"""Revisão 2 da correção do grupo VERSAO (revisão de segurança da 1.7.10, rodada 4), KIT-F1: `scripts/versao_em_uso.py`.

1. Linha do registro partida por U+2028 (média). O registro gravava a linha com ensure_ascii=False, e os leitores a
   partiam com splitlines(), que parte também em U+2028, U+2029 e U+0085: cada pedaço falhava no json.loads e era
   pulado. Com o separador no motivo do pedido de volta ou no decisao_id da decisão (os dois a sessão escreve, e o kit
   verifica a decisão com o decisao_id como está), a troca sumia para todos os leitores: o aceite já usado valia de
   novo, e a última troca não mudava (o A-B-A que a âncora fecha voltava). O substituto isolado (U+DCFF) estourava o
   encode depois da troca (traceback, código 1). Agora a linha vai em ASCII, os leitores partem só em "\\n", a linha
   que não é objeto JSON recusa, o JSON que falha depois da troca sai com código 3, e o motivo e o nome da entrega com
   caractere invisível e o decisao_id fora do formato do kit recusam antes (defesa em profundidade: os cenários fim a
   fim rodam também sem essa camada).
2. Corrida na pasta da cópia (baixa): a sessão trocava outputs/versao por ligação entre a conferência das pastas e a
   gravação da cópia da âncora, e o titular a gravava fora do projeto. Agora, no POSIX, por descritor de pasta; no
   Windows, com o caminho real da pasta conferido antes de pôr o temporário no lugar.
3. Mensagem da âncora vazia (baixa): a proposta honesta feita sem versão em uso, com outra promovida antes dela, ouve
   "mudou", não "não diz qual versão estava em uso".
4. Lacunas de teste da revisão 2 (mutações que sobreviviam): com em-uso/ legível o propor ignora a cópia; o pedido
   confere o formato da âncora, com e sem --para; a cópia de outro projeto é ignorada.
5. Revisão 3 da correção: o registro salvo à mão com BOM (PowerShell 5.1, Bloco de Notas antigo) recusava na linha 1,
   certa à vista, e agora é lido; a corrida dupla na pasta da cópia (trocada por ligação logo antes de uma abertura e
   destrocada logo depois), que só a gravação por descritor fecha no POSIX, ganhou teste; e o nome com caractere
   invisível que vai para o manifesto (item, origem, decisão), que com o substituto isolado estourava o encode dele
   antes da troca (traceback, código 1), recusa com código 2, e o propor o deixa de fora.
A camada da data (baixa) está em test_versao_em_uso_ancora_1710.py (TestMensagemDaData); o pedido com --para, em
TestPedidoComPara do mesmo arquivo. A verificação do kit é simulada, como nos testes do pacote. Raiz fictícia em pasta
temporária.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import itertools
import json
import os
import re
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from apoio import SCRIPTS, criar_ligacao_dir, rodar_script

# Os separadores que o splitlines() parte e o json.dumps(ensure_ascii=False) deixa crus.
SEPARADORES = {"U+2028": "\u2028", "U+2029": "\u2029", "U+0085": "\x85"}


def carregar():
    spec = importlib.util.spec_from_file_location("_teste_versao_registro_1710", SCRIPTS / "versao_em_uso.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


MOD = carregar()


def sha(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def aceite(alvo: dict, **mudar):
    """A verificação simulada do kit: aceite assinado sobre a entrega `alvo`; uma decisão por entrega, como no kit."""
    v = {"valida": True, "tipo": "aceite", "forca": "assinatura", "motivo": "decisão assinada pelo titular",
         "entrega": {"caminho": alvo["entrega"], "sha256": alvo["sha256"]}, "decisao_id": "dec-" + alvo["sha256"][:8],
         "sha256_decisao": sha(b"decisao ficticia de " + alvo["sha256"].encode())}
    v.update(mudar)
    return lambda _raiz, _decisao: v


def sem_a_recusa_do_motivo():
    """Sem a camada que recusa o motivo e o nome da entrega com caractere invisível: o registro sozinho tem de fechar
    o cenário. `create=True`: na contraprova, o código de antes não tem a camada."""
    return mock.patch.object(MOD, "_com_invisivel", return_value=False, create=True)


def sem_a_recusa_do_decisao_id():
    return mock.patch.object(MOD, "DECISAO_ID", re.compile(r".*", re.S), create=True)


class _Raiz(unittest.TestCase):
    def setUp(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="versao-registro-")))
        self.addCleanup(MOD._apagar, self.base)
        self.montar("raiz")

    def montar(self, nome: str) -> None:
        """Uma raiz fictícia nova dentro da pasta temporária (um cenário por raiz)."""
        self.raiz = self.base / nome
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
        self.registro = self.em_uso / "registro.jsonl"
        self.copia = self.projeto / MOD.ESTADO_PARA_A_SESSAO

    def devolver(self, quem: str) -> None:
        """Os bytes de uma versão na pasta de trabalho (a sessão pode devolver os de uma antiga)."""
        (self.trabalho / "util.py").write_bytes(f"QUEM = {quem!r}\n".encode())

    def propor(self, nome: str, quem: str, pasta: str = "outputs/versao") -> dict:
        self.devolver(quem)
        return MOD.propor(self.raiz, "p", self.trabalho, self.lista, self.projeto / pasta / nome)

    def promover(self, proposta: dict, **mudar) -> dict:
        return MOD.promover(self.raiz, "p", proposta["proposta"], proposta["sha256"], self.decisao,
                            verificar=aceite(proposta, **mudar))

    def pedir(self, nome: str = "volta.json", motivo: str = "voltar a anterior (fictício)", **extra) -> dict:
        return MOD.pedir_volta(self.raiz, "p", self.projeto / "outputs" / "versao" / nome, motivo=motivo, **extra)

    def voltar(self, pedido: dict, **mudar) -> dict:
        return MOD.voltar(self.raiz, "p", pedido["pedido"], pedido["sha256"], self.decisao,
                          verificar=aceite(pedido, **mudar))

    def em_uso_agora(self) -> bytes:
        return (self.atual / "util.py").read_bytes()

    def linhas(self) -> tuple[int, int]:
        """(linhas gravadas no registro, linhas que os leitores veem): têm de ser iguais."""
        return self.registro.read_bytes().count(b"\n"), len(MOD._linhas_do_registro(self.registro, "teste") or [])

    def args(self, acao: str, entrega: dict) -> list[str]:
        chave = "proposta" if acao == "promover" else "pedido"
        return [acao, "--raiz", str(self.raiz), "--projeto", "p", f"--{chave}", entrega[chave], f"--{chave}-sha256",
                entrega["sha256"], "--decisao", str(self.decisao)]

    @staticmethod
    def reescrever(entrega: dict, chave: str, **mudar) -> dict:
        """A entrega com campos trocados (quem grava a proposta e o pedido é a sessão), em JSON com escapes: o
        substituto isolado não se grava em UTF-8."""
        dados = json.loads(Path(entrega[chave]).read_bytes())
        dados.update(mudar)
        bruto = (json.dumps(dados, ensure_ascii=True, indent=2) + "\n").encode("ascii")
        Path(entrega[chave]).write_bytes(bruto)
        return {**entrega, "sha256": sha(bruto)}

    @staticmethod
    def ancora(entrega: dict) -> dict:
        dados = json.loads(Path(entrega.get("proposta") or entrega["pedido"]).read_bytes())
        return {k: dados.get(k) for k in MOD.ANCORA}

    @staticmethod
    def escondido():
        """A sessão do Ubuntu: em-uso/ fica fora da leitura e parece ausente."""
        return mock.patch.object(MOD, "_em_uso", lambda raiz, projeto: Path(raiz) / "em-uso-fora-da-leitura" / projeto)


class TestRegistroEmAscii(_Raiz):
    """Item 1, a gravação e a leitura do registro."""

    def test_cada_troca_e_uma_linha_ascii_lida_inteira(self):
        self.em_uso.mkdir(parents=True)
        valores = [*SEPARADORES.values(), "\udcff"]
        for n, sep in enumerate(valores):
            MOD._registrar(self.em_uso, {"acao": "voltar", "motivo": f"a{sep}b", "decisao_id": f"dec{sep}x",
                                         "pedido": f"outputs/v{sep}.json", "pedido_sha256": f"{n:064x}"})
        bruto = self.registro.read_bytes()
        self.assertTrue(bruto.isascii(), bruto[:200])
        self.assertEqual(self.linhas(), (len(valores), len(valores)))
        itens = MOD._linhas_do_registro(self.registro, "teste")
        self.assertEqual([i["motivo"] for i in itens], [f"a{s}b" for s in valores])
        self.assertEqual(MOD._ja_usados(self.registro), {f"{n:064x}" for n in range(len(valores))})

    def test_linha_antiga_com_o_separador_cru_e_lida_inteira(self):
        # Como a versão de antes gravava (ensure_ascii=False): o leitor a lê inteira, e a troca conta.
        self.em_uso.mkdir(parents=True)
        antigas = [{"acao": "voltar", "quando": "2026-11-01T12:00:00+00:00", "motivo": f"a{sep}b",
                    "pedido_sha256": f"{n:064x}", "manifesto_sha256": f"{n + 10:064x}"}
                   for n, sep in enumerate(SEPARADORES.values())]
        self.registro.write_bytes(b"".join((json.dumps(l, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
                                           for l in antigas))
        self.assertEqual(self.linhas(), (len(antigas), len(antigas)))
        self.assertEqual(MOD._ja_usados(self.registro), {l["pedido_sha256"] for l in antigas})
        self.assertEqual(MOD._ativos(self.registro), [l["manifesto_sha256"] for l in antigas])
        self.assertEqual(MOD._ultima_troca(self.registro), sha(json.dumps(antigas[-1], sort_keys=True).encode()))

    def test_linha_que_nao_e_objeto_json_recusa(self):
        # Pulada, ela escondia uma troca: falha fechada, como o registro que não se lê.
        self.promover(self.propor("v0.json", "v0"))
        v1 = self.propor("v1.json", "v1")
        valido = self.registro.read_bytes()
        for nome, lixo in {"truncada": b'{"acao": "promover", "proposta_sha256": "ab', "lista": b"[1, 2]",
                           "texto": b'"promover"', "solta": b"x"}.items():
            with self.subTest(nome):
                self.registro.write_bytes(valido + lixo + b"\n")
                with self.assertRaises(MOD.Recusa) as ctx:
                    MOD._ja_usados(self.registro)
                self.assertIn("linha 2 fora do formato", str(ctx.exception))
                with self.assertRaises(MOD.Recusa) as ctx:
                    self.promover(v1)
                self.assertIn("nada foi trocado", str(ctx.exception))
        r = rodar_script("versao_em_uso.py", "conferir", "--raiz", self.raiz, "--projeto", "p")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v0'\n")
        # A linha em branco e o fim de linha do Windows não são linha fora do formato.
        self.registro.write_bytes(valido.replace(b"\n", b"\r\n") + b"\n  \n")
        self.assertEqual(len(MOD._linhas_do_registro(self.registro, "teste")), 1)
        self.promover(v1)
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v1'\n")

    def test_registro_salvo_com_bom_e_lido(self):
        # Revisão 3 da correção: a recusa acima manda conferir a linha; salvo à mão pelo PowerShell 5.1 (Set-Content ou
        # Out-File -Encoding utf8) ou pelo Bloco de Notas antigo, o registro ganha o BOM, e a linha 1, certa à vista,
        # recusava o promover, o voltar e o conferir. Só o BOM do início sai: no meio, a linha continua fora do formato.
        self.promover(self.propor("v0.json", "v0"))
        v1 = self.propor("v1.json", "v1")
        valido = self.registro.read_bytes()
        self.registro.write_bytes(b"\xef\xbb\xbf" + valido.replace(b"\n", b"\r\n"))
        self.assertEqual(len(MOD._linhas_do_registro(self.registro, "teste")), 1)
        r = rodar_script("versao_em_uso.py", "conferir", "--raiz", self.raiz, "--projeto", "p")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.promover(v1)
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v1'\n")
        self.assertEqual(self.linhas(), (2, 2))
        bruto = self.registro.read_bytes()
        self.registro.write_bytes(bruto + b"\xef\xbb\xbf" + valido)
        with self.assertRaises(MOD.Recusa) as ctx:
            MOD._linhas_do_registro(self.registro, "teste")
        self.assertIn("linha 3 fora do formato", str(ctx.exception))

    def test_json_que_falha_depois_da_troca_sai_com_codigo_3(self):
        self.promover(self.propor("v0.json", "v0"))
        v1 = self.propor("v1.json", "v1")
        estouro = UnicodeEncodeError("utf-8", "\udcff", 0, 1, "surrogates not allowed")
        with mock.patch.object(MOD, "_registrar", side_effect=estouro), \
                mock.patch.object(MOD, "verificar_decisao_pelo_kit", aceite(v1)), \
                mock.patch.object(sys, "stdout", io.StringIO()) as saida, \
                mock.patch.object(sys, "stderr", io.StringIO()):
            self.assertEqual(MOD.main(self.args("promover", v1)), 3, "a troca aconteceu: código 3, não traceback")
        self.assertTrue(json.loads(saida.getvalue())["registro"].startswith("falhou: UnicodeEncodeError"))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v1'\n")


class TestCenariosFimAFim(_Raiz):
    """Item 1, os cenários da revisão 2 sem a camada que recusa o motivo e o decisao_id: o registro sozinho os fecha."""

    def cenario_d(self, sep: str) -> None:
        """v0 e v1 promovidas; q1, q2 e q3, pedidos sem --para com o separador no motivo, voltam um depois do outro (o
        titular termina na v0); o voltar de q2 de novo, o aceite já usado, punha a v1 em uso sem assinatura nova."""
        self.promover(self.propor("v0.json", "v0"))
        self.promover(self.propor("v1.json", "v1"))
        motivo = f"voltar{sep}a anterior (fictício)"
        q1 = self.pedir("q1.json", motivo)
        self.voltar(q1)
        q2 = self.pedir("q2.json", motivo)
        self.voltar(q2)
        q3 = self.pedir("q3.json", motivo)
        self.voltar(q3)
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v0'\n")
        with self.assertRaises(MOD.Recusa) as ctx:
            self.voltar(q2)
        self.assertIn("uma volta só", str(ctx.exception))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v0'\n")
        self.assertEqual(self.linhas(), (5, 5))
        self.assertTrue(MOD.conferir(self.raiz, "p")["ok"])

    def test_cenario_d_com_o_separador_no_motivo(self):
        for n, (nome, sep) in enumerate(SEPARADORES.items()):
            with self.subTest(nome):
                self.montar(f"raiz-d-{n}")
                with sem_a_recusa_do_motivo():
                    self.cenario_d(sep)

    def test_cenario_a_com_o_separador_no_decisao_id(self):
        # A v1 promovida com o decisao_id partido e a volta com o motivo partido: a âncora de agora voltava a ser a da
        # proposta da v1, e o aceite dela, já usado, a repunha.
        for n, (nome, sep) in enumerate(SEPARADORES.items()):
            with self.subTest(nome):
                self.montar(f"raiz-a-{n}")
                with sem_a_recusa_do_motivo(), sem_a_recusa_do_decisao_id():
                    self.promover(self.propor("v0.json", "v0"))
                    v1 = self.propor("v1.json", "v1")
                    self.promover(v1, decisao_id=f"dec-v1{sep}x")
                    self.voltar(self.pedir(motivo=f"voltar{sep}a v0"))
                    self.assertEqual(self.em_uso_agora(), b"QUEM = 'v0'\n")
                    self.devolver("v1")
                    with self.assertRaises(MOD.Recusa) as ctx:
                        self.promover(v1, decisao_id=f"dec-v1{sep}x")
                self.assertIn("uma promoção só", str(ctx.exception))
                self.assertEqual(self.em_uso_agora(), b"QUEM = 'v0'\n")
                self.assertEqual(self.linhas(), (3, 3))

    def test_motivo_com_substituto_isolado_vai_escapado_e_a_volta_conta(self):
        # Antes, o encode da linha estourava depois da troca: traceback (código 1), a troca fora do registro.
        self.promover(self.propor("v0.json", "v0"))
        self.promover(self.propor("v1.json", "v1"))
        pedido = self.reescrever(self.pedir(), "pedido", motivo="voltar \udcff")
        with sem_a_recusa_do_motivo(), mock.patch.object(MOD, "verificar_decisao_pelo_kit", aceite(pedido)), \
                mock.patch.object(sys, "stdout", io.StringIO()), mock.patch.object(sys, "stderr", io.StringIO()):
            self.assertEqual(MOD.main(self.args("voltar", pedido)), 0)
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v0'\n")
        self.assertIn(pedido["sha256"], MOD._ja_usados(self.registro))
        self.assertEqual(self.linhas(), (3, 3))


class TestRecusaAntesDaTroca(_Raiz):
    """Item 1, a defesa em profundidade: o motivo, o nome da entrega e o decisao_id que a sessão escreve."""

    INVISIVEIS = {**SEPARADORES, "U+DCFF": "\udcff", "U+202E": "\u202e", "U+200B": "\u200b", "ESC": "\x1b",
                  "LF": "\n"}

    def setUp(self):
        super().setUp()
        self.promover(self.propor("v0.json", "v0"))
        self.promover(self.propor("v1.json", "v1"))

    def test_motivo_com_caractere_invisivel(self):
        for n, (nome, c) in enumerate(self.INVISIVEIS.items()):
            with self.subTest(nome):
                with self.assertRaises(MOD.Recusa):
                    self.pedir(f"sessao-{n}.json", f"voltar{c}x")
                pedido = self.reescrever(self.pedir(f"forjado-{n}.json"), "pedido", motivo=f"voltar{c}x")
                with self.assertRaises(MOD.Recusa) as ctx:
                    self.voltar(pedido)
                self.assertIn("motivo fora do formato", str(ctx.exception))
                self.assertIn("nada foi trocado", str(ctx.exception))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v1'\n")
        self.assertEqual(self.linhas(), (2, 2))

    def test_motivo_com_substituto_isolado_pela_linha_de_comando_recusa_com_codigo_2(self):
        pedido = self.reescrever(self.pedir(), "pedido", motivo="voltar \udcff")
        with mock.patch.object(MOD, "verificar_decisao_pelo_kit", aceite(pedido)), \
                mock.patch.object(sys, "stdout", io.StringIO()), \
                mock.patch.object(sys, "stderr", io.StringIO()) as erro:
            self.assertEqual(MOD.main(self.args("voltar", pedido)), 2, "recusa antes da troca, nunca traceback")
        self.assertIn("motivo fora do formato", json.loads(erro.getvalue())["erro"])
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v1'\n")

    def test_entrega_com_separador_no_nome(self):
        v2 = self.propor("v2\u2028x.json", "v2")
        with self.assertRaises(MOD.Recusa) as ctx:
            self.promover(v2)
        self.assertIn("no nome", str(ctx.exception))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v1'\n")

    def test_decisao_id_ou_sha256_da_decisao_fora_do_formato(self):
        v2 = self.propor("v2.json", "v2")
        for valor in ("dec-v2\u2028x", "dec v2", "", "-dec", "d" * 101, None, 5):
            with self.subTest(decisao_id=ascii(valor)):
                with self.assertRaises(MOD.Recusa) as ctx:
                    self.promover(v2, decisao_id=valor)
                self.assertIn("decisao_id fora do formato", str(ctx.exception))
        for valor in (None, "xyz", 5):
            with self.subTest(sha256_decisao=valor):
                with self.assertRaises(MOD.Recusa) as ctx:
                    self.promover(v2, sha256_decisao=valor)
                self.assertIn("SHA-256 da decisão", str(ctx.exception))
        with self.assertRaises(MOD.Recusa) as ctx:
            self.voltar(self.pedir(), decisao_id="dec\u2029x")
        self.assertIn("decisao_id fora do formato", str(ctx.exception))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v1'\n")
        self.assertEqual(self.linhas(), (2, 2))
        self.promover(v2, decisao_id="dec-v2.1_a")  # no formato do kit, vale
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v2'\n")

    # Os criáveis no NTFS e no ext4 (no Windows, o nome não leva controle de U+0000 a U+001F).
    NO_MANIFESTO = {"U+DCFF": INVISIVEIS["U+DCFF"], "U+2028": INVISIVEIS["U+2028"], "U+202E": INVISIVEIS["U+202E"]}

    def test_nome_que_vai_para_o_manifesto_com_caractere_invisivel_recusa_com_codigo_2(self):
        # Revisão 3 da correção (a sonda 4 da revisão 3): o item da proposta, a origem e o nome da decisão vão para o
        # manifesto; com o substituto isolado, o encode dele estourava depois da cópia, antes da troca (traceback,
        # código 1). Os arquivos existem com esses nomes: só a recusa pelo nome os barra.
        base, pela_cli = self.propor("v2.json", "v2"), None
        for n, (nome, c) in enumerate(self.NO_MANIFESTO.items()):
            for onde in ("item", "origem", "decisao"):
                with self.subTest(nome, onde=onde):
                    dados, decisao = json.loads(Path(base["proposta"]).read_bytes()), self.decisao
                    if onde == "item":
                        (self.trabalho / f"util{c}.py").write_bytes(b"QUEM = 'v2'\n")
                        dados["arquivos"] = [{**a, "caminho": f"util{c}.py"} for a in dados["arquivos"]]
                    elif onde == "origem":
                        (self.projeto / f"trabalho{c}").mkdir()
                        (self.projeto / f"trabalho{c}" / "util.py").write_bytes(b"QUEM = 'v2'\n")
                        dados["origem"] = f"trabalho{c}"
                    else:
                        decisao = self.projeto / "decisoes" / f"dec{c}.json"
                    bruto = (json.dumps(dados, ensure_ascii=True, indent=2) + "\n").encode("ascii")
                    arquivo = self.projeto / "outputs" / "versao" / f"forjada-{n}-{onde}.json"
                    arquivo.write_bytes(bruto)
                    entrega = {"proposta": str(arquivo), "sha256": sha(bruto),
                               "entrega": f"outputs/versao/{arquivo.name}"}
                    args = [*self.args("promover", entrega)[:-1], str(decisao)]
                    if (nome, onde) == ("U+DCFF", "item"):
                        pela_cli = args
                    with mock.patch.object(MOD, "verificar_decisao_pelo_kit", aceite(entrega)), \
                            mock.patch.object(sys, "stdout", io.StringIO()), \
                            mock.patch.object(sys, "stderr", io.StringIO()) as erro:
                        self.assertEqual(MOD.main(args), 2, "recusa antes da troca, nunca traceback")
                    self.assertIn("nada foi trocado" if onde == "decisao" else "fora do formato" if onde == "item"
                                  else "origem válida", json.loads(erro.getvalue())["erro"])
        # Pela linha de comando de verdade (a recusa vem antes do kit): o stderr leva o JSON, sem traceback.
        r = rodar_script("versao_em_uso.py", *pela_cli)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("fora do formato", json.loads(r.stderr)["erro"])
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v1'\n")
        self.assertEqual([n for n in os.listdir(self.em_uso) if n.startswith(".")], [], "preparo ou trava sobrou")
        self.assertEqual(self.linhas(), (2, 2))

    def test_propor_deixa_de_fora_o_nome_com_caractere_invisivel(self):
        for c in self.NO_MANIFESTO.values():
            (self.trabalho / f"util{c}.py").write_bytes(b"QUEM = 'outro'\n")
        v2 = self.propor("v2.json", "v2")
        dados = json.loads(Path(v2["proposta"]).read_bytes())
        self.assertEqual([a["caminho"] for a in dados["arquivos"]], ["util.py"])
        self.assertEqual(sorted(e["caminho"] for e in dados["excluidos"] if "renomeie" in e["motivo"]),
                         sorted(ascii(f"util{c}.py") for c in self.NO_MANIFESTO.values()))
        self.promover(v2)
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v2'\n")


class TestCorridaNaPastaDaCopia(_Raiz):
    """Item 2: a sessão troca outputs/versao por ligação logo antes da primeira abertura da gravação da cópia (depois
    de toda conferência pelo caminho, como a sonda da revisão 2): nada é gravado fora do projeto, o resultado diz
    "falhou" e o aviso vai para o stderr; a troca aconteceu (código 0)."""

    def test_pasta_trocada_por_ligacao_no_meio_da_gravacao(self):
        fora = self.base / "fora"
        fora.mkdir()
        self.promover(self.propor("v0.json", "v0", pasta="outputs"))  # a pasta da cópia fica só com a cópia
        self.assertTrue(self.copia.is_file())
        v1 = self.propor("v1.json", "v1", pasta="outputs")
        versao, abrir, trocou = self.copia.parent, os.open, []

        def abrir_trocando(*args, **kwargs):
            if not trocou:
                trocou.append(versao.rename(versao.with_name("versao-antes")))
                criar_ligacao_dir(versao, fora)
            return abrir(*args, **kwargs)

        publicar = MOD._publicar_estado

        def com_corrida(*args, **kwargs):
            with mock.patch.object(os, "open", side_effect=abrir_trocando):
                return publicar(*args, **kwargs)

        with mock.patch.object(MOD, "_publicar_estado", com_corrida), \
                mock.patch.object(MOD, "verificar_decisao_pelo_kit", aceite(v1)), \
                mock.patch.object(sys, "stdout", io.StringIO()) as saida, \
                mock.patch.object(sys, "stderr", io.StringIO()) as erro:
            codigo = MOD.main(self.args("promover", v1))
        self.assertEqual(len(trocou), 1, "a pasta foi trocada no meio da gravação")
        self.assertEqual(os.listdir(fora), [], "nada gravado fora do projeto")
        self.assertEqual(codigo, 0, "a troca aconteceu: nem recusa (2) nem registro falho (3)")
        self.assertTrue(json.loads(saida.getvalue())["estado_para_a_sessao"].startswith("falhou:"))
        self.assertIn("não foi gravada", json.loads(erro.getvalue())["aviso"])
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v1'\n")

    def promover_com_corrida_dupla(self, proposta: dict, fora: Path, quando) -> tuple[dict, int]:
        """O promover com a sessão trocando outputs/versao por ligação logo antes da abertura em que `quando(args)` é
        verdade, e destrocando logo depois dela; (resultado, quantas vezes trocou)."""
        versao, antes, abrir, trocou = self.copia.parent, self.copia.parent.with_name("versao-antes"), os.open, []

        def abrir_trocando(*args, **kwargs):
            if trocou or not quando(args):
                return abrir(*args, **kwargs)
            trocou.append(versao.rename(antes))
            criar_ligacao_dir(versao, fora)
            try:
                return abrir(*args, **kwargs)
            finally:
                os.unlink(versao)
                antes.rename(versao)

        publicar = MOD._publicar_estado

        def com_corrida(*args, **kwargs):
            with mock.patch.object(os, "open", side_effect=abrir_trocando):
                return publicar(*args, **kwargs)

        with mock.patch.object(MOD, "_publicar_estado", com_corrida):
            return self.promover(proposta), len(trocou)

    @unittest.skipIf(os.name == "nt", "resíduo declarado do Windows: isolamento lógico (a gravação é pelo caminho)")
    def test_pasta_trocada_e_destrocada_em_volta_de_uma_abertura(self):
        # Revisão 3 da correção (lente regressão): a corrida dupla. Pelo caminho com o realpath conferido (o ramo do
        # Windows), o temporário ia para fora e a cópia falhava; por descritor de pasta, cada abertura é relativa à
        # pasta já aberta: nada sai do projeto, e a cópia é gravada.
        fora = self.base / "fora"
        fora.mkdir()
        self.promover(self.propor("v0.json", "v0", pasta="outputs"))  # a pasta da cópia fica só com a cópia
        momentos = {"a primeira abertura": lambda args: True,
                    "a criação do temporário": lambda args: len(args) > 1 and bool(args[1] & os.O_CREAT)}
        for n, (momento, quando) in enumerate(momentos.items(), 1):
            with self.subTest(momento):
                res, trocas = self.promover_com_corrida_dupla(self.propor(f"v{n}.json", f"v{n}", pasta="outputs"),
                                                              fora, quando)
                self.assertEqual(trocas, 1, "a pasta foi trocada e destrocada no meio da gravação")
                self.assertEqual(os.listdir(fora), [], "nada gravado fora do projeto")
                self.assertEqual(res["estado_para_a_sessao"], str(self.copia))
                self.assertNotIn("aviso", res)
                self.assertEqual(os.listdir(self.copia.parent), [self.copia.name], "nem temporário sobrando")
                self.assertEqual(MOD._ler_estado(self.projeto, "p"), MOD._estado_em_uso(self.em_uso))
                self.assertEqual(self.em_uso_agora(), f"QUEM = 'v{n}'\n".encode())


class TestMensagemDaAncoraVazia(_Raiz):
    """Item 3: a âncora vazia é legítima quando nada estava em uso; se outra proposta entrou antes, a causa é a mesma do
    "mudou" (a mensagem "vazia" mandava procurar um defeito de leitura que não existe)."""

    def setUp(self):
        super().setUp()
        # Cada instante um segundo depois do anterior (revisão 3 da correção): o relógio do Python 3.12 no Windows anda
        # de 15,6 ms em 15,6 ms, e a linha da promoção de `a` empatava com a data da proposta `b`, feita antes dela (7
        # em 200 na sonda): sem troca registrada "depois" dela, a mensagem era a da âncora vazia, e o teste caía.
        inicio, passo = datetime.now(timezone.utc) - timedelta(hours=1), itertools.count()
        relogio = mock.patch.object(MOD, "_instante", side_effect=lambda: (
            inicio + timedelta(seconds=next(passo))).isoformat(timespec="microseconds"))
        relogio.start()
        self.addCleanup(relogio.stop)

    def test_proposta_feita_sem_versao_em_uso_com_outra_promovida_antes(self):
        a, b = self.propor("a.json", "a"), self.propor("b.json", "b")
        self.assertEqual(self.ancora(b), dict.fromkeys(MOD.ANCORA), "sem versão em uso, a âncora é vazia")
        self.devolver("a")
        self.promover(a)
        self.devolver("b")
        with self.assertRaises(MOD.Recusa) as ctx:
            self.promover(b)
        self.assertIn("mudou depois da proposta", str(ctx.exception))
        self.assertNotIn("não diz qual versão", str(ctx.exception))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'a'\n")
        self.promover(self.propor("b-de-novo.json", "b"))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'b'\n")


class TestLacunasDaAncora(_Raiz):
    """Item 4: os comportamentos da revisão 1 que nenhum teste prendia."""

    def test_com_em_uso_legivel_o_propor_ignora_a_copia(self):
        # A sessão do Windows (ou com a raiz em /mnt/e) lê em-uso/: a cópia vencida ou forjada não conta.
        self.promover(self.propor("v0.json", "v0"))
        forjada = {**json.loads(self.copia.read_bytes()), "manifesto_em_uso": "0" * 64, "ultima_troca": "1" * 64}
        self.copia.write_bytes(json.dumps(forjada).encode("utf-8"))
        v1 = self.propor("v1.json", "v1")
        self.assertEqual(self.ancora(v1), MOD._estado_em_uso(self.em_uso))
        self.promover(v1)  # na primeira tentativa
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v1'\n")

    def test_pedido_com_ancora_fora_do_formato_recusa_com_e_sem_para(self):
        self.promover(self.propor("v0.json", "v0"))
        self.promover(self.propor("v1.json", "v1"))
        primeira = sorted(os.listdir(self.em_uso / "anteriores"))[0]
        for n, (para, campo, valor) in enumerate(itertools.product((None, primeira), MOD.ANCORA, ("xyz", 5))):
            with self.subTest(para=para, campo=campo, valor=valor):
                pedido = self.pedir(f"formato-{n}.json", **({"para": para} if para else {}))
                with self.assertRaises(MOD.Recusa) as ctx:
                    self.voltar(self.reescrever(pedido, "pedido", **{campo: valor}))
                self.assertIn("fora do formato", str(ctx.exception))
        self.assertEqual(self.em_uso_agora(), b"QUEM = 'v1'\n")

    def test_copia_de_outro_projeto_ou_de_outro_esquema_e_ignorada(self):
        self.promover(self.propor("v0.json", "v0"))
        copia = json.loads(self.copia.read_bytes())
        self.assertEqual(MOD._ler_estado(self.projeto, "p"), MOD._estado_em_uso(self.em_uso))
        for n, mudar in enumerate(({"projeto": "outro"}, {"schema_version": "outro/1"})):
            with self.subTest(mudar=mudar):
                self.copia.write_bytes(json.dumps({**copia, **mudar}).encode("utf-8"))
                self.assertIsNone(MOD._ler_estado(self.projeto, "p"))
                with self.escondido():
                    v1 = self.propor(f"v1-{n}.json", "v1")
                self.assertEqual(self.ancora(v1), dict.fromkeys(MOD.ANCORA))


if __name__ == "__main__":
    unittest.main()
