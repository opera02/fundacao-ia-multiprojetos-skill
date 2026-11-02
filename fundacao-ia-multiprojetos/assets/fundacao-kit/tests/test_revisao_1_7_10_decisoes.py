"""Revisão de segurança da 1.7.10, grupo KITDEC: os arquivos das decisões e da conclusão da tarefa, que o kit rodado
pelo porteiro lê e grava em projects/<p>/, passam pelo descritor da pasta conferida (core/disco_projeto.py e
core/decisoes_disco.py).

- POR-01: decisoes/ (ou outputs/runs/) trocada por uma ligação entre a conferência e a gravação levava a decisão, a
  linha do registro e a saída da etapa do aceite para fora do projeto. Aqui a troca é feita no último passo antes da
  gravação, pelo dublê da função chamada ali (no Windows, junção); a sonda em laço, com o kit rodando pelo porteiro,
  fica em scripts/tests/test_porteiro_decisoes.py.
- POR-02: registro.jsonl e <decisão>.json.sig ligados a um arquivo de outro projeto devolviam à sessão o SHA-256 dele e
  o byte e a posição do primeiro erro de UTF-8 (traceback); a exceção inesperada agora sai pelo contrato da CLI.
- POR-03: um FIFO no lugar da decisão (ou da saída da etapa do aceite) travava o kit, com a vez do banco na mão, até o
  prazo do porteiro; agora é recusado na hora (só no POSIX, onde há FIFO).
- Revisão 1 do grupo: o acréscimo ao registro também abre sem esperar (o FIFO trocado no nome depois da conferência e
  o arrendamento de outro processo, F_SETLEASE, só no Linux); o registro é analisado só até o teto de linhas e de
  bytes; ENXIO e EWOULDBLOCK na abertura são recusa; com o aceite válido e o registro ligado, a conclusão não lê o
  alvo; o RuntimeError do kit (banco de versão futura) sai pelo contrato com a mensagem.
Dados fictícios; chave e âncora de ENSAIO. O kit de antes falha aqui (contraprova no relatório do grupo).
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import unittest
from pathlib import Path
from unittest import mock

from apoio_auditoria import criar_ligacao_dir, trocar_pasta_por_ligacao
from test_auditoria_1_7_6_publicacao import ligar, tipos_de_ligacao
from test_decisoes_cli import DecisoesCliCase

from fundacao.core import db, decisoes, tasks

try:  # o módulo da correção; o kit de antes não o tem (a troca do teste da saída da etapa usa o dublê de lá)
    from fundacao.core import decisoes_disco
except ImportError:  # pragma: no cover - só na contraprova
    decisoes_disco = None

FIFO = os.name == "posix" and hasattr(os, "mkfifo")
ARRENDAMENTO = sys.platform.startswith("linux")  # F_SETLEASE; o sistema de arquivos ainda pode recusar (pula)
# O arquivo fictício do outro projeto tem 0xff na posição 25, como na sonda B1 do achado.
SEGREDO = b"conteudo ficticio do proj\xff e o resto, tambem ficticio\n"
# Os tetos da revisão 1 (o kit de antes não os tem: a contraprova usa os mesmos números).
TETO_LINHAS = getattr(decisoes_disco, "TETO_LINHAS_REGISTRO", 50_000)
TETO_BYTES = decisoes_disco.TETO_REGISTRO if hasattr(decisoes_disco, "TETO_LINHAS_REGISTRO") else 8 << 20
# Segura um arrendamento (F_SETLEASE) no arquivo, como a sessão pode fazer num arquivo do próprio projeto, até ser
# encerrado; o aviso de quebra (SIGIO) é ignorado, como faria quem quer prender a abertura dos outros.
SEGURAR_ARRENDAMENTO = "\n".join((
    "import fcntl, os, signal, sys",
    "signal.signal(signal.SIGIO, signal.SIG_IGN)",
    "fd = os.open(sys.argv[1], os.O_RDONLY)",
    "tipo = fcntl.F_RDLCK if sys.argv[2] == 'leitura' else fcntl.F_WRLCK",
    "try:",
    "    fcntl.fcntl(fd, getattr(fcntl, 'F_SETLEASE', 1024), tipo)",
    "except OSError as exc:",
    "    sys.stdout.write(f'indisponivel errno {exc.errno}\\n')",
    "    sys.stdout.flush()",
    "    sys.exit(3)",
    "sys.stdout.write('pronto\\n')",
    "sys.stdout.flush()",
    "sys.stdin.read()",
))


class KitdecCase(DecisoesCliCase):
    def setUp(self):
        super().setUp()
        self.outro = self.root / "projects" / "reversa-lab"
        self.vitima = self.outro / "notas" / "segredo-ficticio.txt"
        self.vitima.parent.mkdir(parents=True, exist_ok=True)
        self.vitima.write_bytes(SEGREDO)
        self.sha_vitima = hashlib.sha256(SEGREDO).hexdigest()

    def kit(self, *args) -> tuple[int, dict | None, str]:
        """A CLI no próprio processo; a exceção que o kit de antes deixava sair vira o traceback que a sessão via."""
        try:
            return self.cli("operador-lab", *args)
        except Exception:  # noqa: BLE001 - é o que se mede
            return 1, None, traceback.format_exc()

    def sem_vazar(self, resposta: tuple, *proibidos: str) -> None:
        codigo, r, erro = resposta
        tudo = json.dumps(r, ensure_ascii=False) + erro
        for texto in ("Traceback", "0xff", "position 25", *proibidos):
            self.assertNotIn(texto, tudo, resposta)
        self.assertIn(codigo, (2, 3), resposta)

    def troca_no_meio(self, original, pasta: Path, alvo: Path, antes=None, feito=None):
        """Dublê de `original`: na primeira chamada (de todos os dublês que dividem `feito`), troca `pasta` por uma
        ligação para `alvo` e segue (a troca da corrida, depois da conferência e antes da gravação)."""
        feito = [] if feito is None else feito

        def duble(*args, **kwargs):
            if not feito:
                if antes is not None:
                    antes(*args)
                feito.append(trocar_pasta_por_ligacao(pasta, alvo))
            return original(*args, **kwargs)
        return duble

    def aceite_registrado(self) -> Path:
        arq = self.preparada()
        self.chaves.assinar(arq)
        codigo, r, erro = self.kit("decisao", "registrar", "--arquivo", str(arq))
        self.assertEqual(codigo, 0, (r, erro))
        return arq


class TestGravacaoNaoSaiDoProjeto(KitdecCase):
    """POR-01: decisão, linha do registro e saída da etapa só na pasta conferida, nunca na de fora."""

    def setUp(self):
        super().setUp()
        self.dec = self.pasta / "decisoes"
        self.dec.mkdir(exist_ok=True)
        self.fora = self.outro / "decisoes"
        self.fora.mkdir(exist_ok=True)

    def test_preparar_com_decisoes_trocada_depois_da_conferencia(self):
        duble = self.troca_no_meio(decisoes.comando_para_o_titular, self.dec, self.fora)
        with mock.patch.object(decisoes, "comando_para_o_titular", duble):
            resposta = self.preparar("operador-lab", "aceite", "outputs/entrega.md", None, "--decisao-id", "corrida-1")
        self.assertEqual(sorted(p.name for p in self.fora.iterdir()), [], resposta)
        codigo, _r, erro = resposta
        if codigo == 0:  # gravada pelo descritor: na pasta conferida, que agora se chama decisoes.original
            self.assertTrue((self.pasta / "decisoes.original" / "corrida-1.json").is_file())
        else:  # no Windows, a cadeia é conferida de novo antes de gravar: a junção recusa
            self.assertIn("E_PATH_ESCAPE", erro)

    def test_registrar_com_decisoes_trocada_depois_da_conferencia(self):
        arq = self.preparada()
        self.chaves.assinar(arq)
        alheio = self.fora / "registro.jsonl"
        alheio.write_bytes(b'{"decisao_id": "dec-alheia-ficticia", "tipo": "aceite"}\n')
        antes = alheio.read_bytes()
        duble = self.troca_no_meio(decisoes.registros_na_trilha, self.dec, self.fora)
        with mock.patch.object(decisoes, "registros_na_trilha", duble):
            resposta = self.kit("decisao", "registrar", "--arquivo", str(arq))
        self.assertEqual(alheio.read_bytes(), antes, resposta)
        self.assertEqual(sorted(p.name for p in self.fora.iterdir()), ["registro.jsonl"], resposta)

    def test_concluir_com_outputs_runs_trocada_antes_da_saida_da_etapa(self):
        arq = self.aceite_registrado()
        runs = self.pasta / "outputs" / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        alvo = self.outro / "outputs" / "runs-alvo"
        alvo.mkdir(parents=True)

        def preparar_alvo(*args):  # a pasta da execução precisa existir do outro lado para a gravação seguir
            primeiro = args[0]
            caminho = Path(primeiro.caminho) if hasattr(primeiro, "caminho") else Path(primeiro).parent
            (alvo / caminho.name).mkdir(exist_ok=True)

        feito: list = []  # uma troca só, pela primeira das duas gravações que o kit fizer
        dubles = [mock.patch.object(tasks, "publicar", self.troca_no_meio(tasks.publicar, runs, alvo, preparar_alvo,
                                                                           feito))]
        if decisoes_disco is not None:
            dubles.append(mock.patch.object(decisoes_disco.Pasta, "trocar", self.troca_no_meio(
                decisoes_disco.Pasta.trocar, runs, alvo, preparar_alvo, feito)))
        for d in dubles:
            d.start()
            self.addCleanup(d.stop)
        resposta = self.kit("tarefa", "concluir", "--decisao", str(arq))
        self.assertEqual([p for p in alvo.rglob("*") if p.is_file()], [], resposta)


class TestLeituraNaoSegueLigacao(KitdecCase):
    """POR-02: o registro e a assinatura ligados a um arquivo de outro projeto não são lidos."""

    def setUp(self):
        super().setUp()
        self.tipos = tipos_de_ligacao(self.root)

    @staticmethod
    def desligar(caminho: Path) -> None:
        if caminho.is_symlink() or caminho.exists():
            caminho.unlink()

    def test_registro_ligado_nao_devolve_byte_nem_posicao_do_erro_de_utf8(self):
        arq = self.preparada()  # nem assinada nem registrada: o kit de antes lia o registro mesmo assim
        reg = self.pasta / "decisoes" / "registro.jsonl"
        for tipo in self.tipos:
            with self.subTest(tipo=tipo):
                self.desligar(reg)
                ligar(reg, self.vitima, tipo)
                self.sem_vazar(self.kit("tarefa", "concluir", "--decisao", str(arq)))
        self.desligar(reg)
        self.assertEqual(self.vitima.read_bytes(), SEGREDO)

    def test_aceite_valido_com_o_registro_ligado_conclui_sem_ler_o_alvo(self):
        # Revisão 1: o teste acima passa pelo atalho (a decisão inválida nem abre o registro). Aqui o aceite é válido e
        # registrado, e a conclusão lê o registro (decisao_vigente): ligado ao arquivo do outro projeto, recusa.
        arq = self.aceite_registrado()
        reg = self.pasta / "decisoes" / "registro.jsonl"
        for tipo in self.tipos:
            with self.subTest(tipo=tipo):
                self.desligar(reg)
                ligar(reg, self.vitima, tipo)
                resposta = self.kit("tarefa", "concluir", "--decisao", str(arq))
                self.sem_vazar(resposta, self.sha_vitima)
                self.assertIn("E_PATH_ESCAPE", resposta[2], resposta)
                self.assertFalse(resposta[1] and resposta[1].get("concluida"), resposta)
        self.desligar(reg)
        self.assertEqual(self.vitima.read_bytes(), SEGREDO)

    def test_registro_do_proprio_projeto_fora_do_utf8_responde_pelo_contrato(self):
        arq = self.preparada()
        self.chaves.assinar(arq)  # aceite válido: a conclusão lê o registro
        (self.pasta / "decisoes" / "registro.jsonl").write_bytes(SEGREDO)
        resposta = self.kit("tarefa", "concluir", "--decisao", str(arq))
        self.sem_vazar(resposta)
        self.assertEqual(json.loads(resposta[2].strip().splitlines()[-1])["error"]["code"], "E_VALIDATION", resposta)

    def test_entrega_com_vinculo_fisico_nao_entra_na_decisao(self):
        entrega = self.pasta / "outputs" / "atalho.md"
        try:
            os.link(self.vitima, entrega)
        except OSError as exc:
            self.skipTest(f"vínculo físico indisponível: {exc}")
        resposta = self.preparar("operador-lab", "aceite", "outputs/atalho.md")
        self.sem_vazar(resposta, self.sha_vitima)
        self.assertIn("E_PATH_ESCAPE", resposta[2])
        self.assertFalse(any((self.pasta / "decisoes").glob("*.json")) if (self.pasta / "decisoes").exists() else False)

    def test_assinatura_ligada_nao_devolve_o_sha256_do_alvo(self):
        arq = self.preparada()
        sig = Path(str(arq) + ".sig")
        for tipo in self.tipos:
            for acao in ("verificar", "registrar"):
                with self.subTest(tipo=tipo, acao=acao):
                    self.desligar(sig)
                    ligar(sig, self.vitima, tipo)
                    resposta = self.kit("decisao", acao, "--arquivo", str(arq))
                    self.sem_vazar(resposta, self.sha_vitima)
                    self.assertFalse(resposta[1] is not None and resposta[1].get("valida"), resposta)
        self.desligar(sig)
        self.assertEqual(self.eventos(decisoes.EVENTO_ASSINADA), 0)

    def test_excecao_inesperada_sai_pelo_contrato_sem_a_mensagem(self):
        arq = self.preparada()
        for exc in (UnicodeDecodeError("utf-8", SEGREDO, 25, 26, "invalid start byte"),
                    KeyError("trecho-ficticio-de-outro-projeto")):
            with self.subTest(exc=type(exc).__name__):
                with mock.patch.object(decisoes, "verificar_decisao", side_effect=exc):
                    codigo, r, erro = self.kit("decisao", "verificar", "--arquivo", str(arq))
                self.assertEqual(codigo, 2, erro)
                self.assertIsNone(r)
                falha = json.loads(erro.strip().splitlines()[-1])["error"]
                self.assertEqual((falha["code"], falha["tipo"]), ("E_INESPERADO", type(exc).__name__))
                self.assertNotIn("trecho-ficticio", erro)
                self.sem_vazar((codigo, r, erro))

    def test_banco_de_versao_futura_sai_pelo_contrato_com_a_mensagem_do_kit(self):
        # Revisão 1: o RuntimeError do db.py é texto fixo do kit, sem bytes de arquivo; o titular precisa do motivo
        # (references/atualizacao-1.7.9.md: o kit anterior recusa versão futura). Antes: traceback (código 1) e, na
        # primeira correção, só "erro inesperado".
        self.con.execute(f"PRAGMA user_version = {len(db.MIGRATIONS) + 1}")
        codigo, r, erro = self.kit("status")
        self.assertEqual((codigo, r), (2, None), erro)
        falha = json.loads(erro.strip().splitlines()[-1])["error"]
        self.assertEqual((falha["code"], falha["tipo"], falha["message"]),
                         ("E_INESPERADO", "RuntimeError", "banco de versão futura; este kit não pode migrá-lo"))
        self.sem_vazar((codigo, r, erro))


class TestPastaDoProjeto(unittest.TestCase):
    """A primitiva (core/disco_projeto.py): teto, resumo, arquivo novo que não sobrescreve e pasta ligada recusada."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="disco-projeto-"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.projeto = self.base / "projects" / "proj-ficticio"
        (self.projeto / "outputs").mkdir(parents=True)
        (self.projeto / "outputs" / "nota.md").write_bytes(b"nota ficticia\n")

    def test_teto_resumo_e_arquivo_novo(self):
        from fundacao.core import disco_projeto
        from fundacao.core.contracts import AlreadyExists, PathEscape
        with disco_projeto.Pasta(self.projeto, ("outputs",)) as pasta:
            self.assertEqual(pasta.ler("nota.md", 64, resumo=True), hashlib.sha256(b"nota ficticia\n").hexdigest())
            self.assertIsNone(pasta.ler("ausente.md", 64))
            with self.assertRaises(PathEscape):
                pasta.ler("nota.md", 4)  # acima do teto: nada é lido
        with disco_projeto.Pasta(self.projeto, ("decisoes", "sub")) as pasta:  # as partes nascem na gravação
            pasta.criar_novo("d.json", b"{}\n")
            with self.assertRaises(AlreadyExists):
                pasta.criar_novo("d.json", b"outra\n")
            self.assertEqual(pasta.ler("d.json", 64), b"{}\n")

    def test_pasta_ligada_e_recusada(self):
        from fundacao.core import disco_projeto
        from fundacao.core.contracts import PathEscape
        fora = self.base / "fora"
        fora.mkdir()
        criar_ligacao_dir(self.projeto / "decisoes", fora)
        for partes in (("decisoes",), ("decisoes", "sub")):
            with self.subTest(partes=partes):
                with self.assertRaises(PathEscape):
                    with disco_projeto.Pasta(self.projeto, partes) as pasta:
                        pasta.criar_novo("d.json", b"{}\n")
        self.assertEqual(list(fora.iterdir()), [])

    def test_fifo_sem_leitor_pasta_renomeada_e_arrendamento_recusam_na_hora(self):
        # Revisão 1 do KITDEC: ENXIO (FIFO sem leitor na abertura sem espera; no DrvFs, a pasta aberta e depois
        # renomeada) e EWOULDBLOCK (arrendamento de outro processo) viram recusa, como a ligação; nada é gravado.
        from fundacao.core import disco_projeto
        from fundacao.core.contracts import PathEscape
        alvo = self.projeto / "outputs" / "d.json"
        alvo.write_bytes(b"{}\n")
        abrir, examinar, examinar_sem_seguir = os.open, os.stat, os.lstat
        for numero in (errno.ENXIO, errno.EWOULDBLOCK):
            def falha(original):
                def duble(caminho, *args, **kwargs):
                    if os.path.basename(os.fsdecode(caminho)) == "d.json":
                        raise OSError(numero, os.strerror(numero), "d.json")
                    return original(caminho, *args, **kwargs)
                return duble
            with disco_projeto.Pasta(self.projeto, ("outputs",)) as pasta:
                with mock.patch.object(disco_projeto.os, "open", falha(abrir)):
                    for nome, operacao in (("ler", lambda: pasta.ler("d.json", 64)),
                                           ("criar_novo", lambda: pasta.criar_novo("d.json", b"[]\n")),
                                           ("anexar", lambda: pasta.anexar("d.json", b"[]\n"))):
                        with self.subTest(errno=errno.errorcode[numero], operacao=nome), \
                                self.assertRaises(PathEscape):
                            operacao()
                if numero == errno.ENXIO:  # o exame do nome (lstat) na pasta aberta e renomeada, no DrvFs
                    with mock.patch.object(disco_projeto.os, "stat", falha(examinar)), \
                            mock.patch.object(disco_projeto.os, "lstat", falha(examinar_sem_seguir)), \
                            self.subTest(errno="ENXIO", operacao="lstat"), self.assertRaises(PathEscape):
                        pasta.lstat("d.json")
        self.assertEqual(alvo.read_bytes(), b"{}\n")


class NaoTravaCase(KitdecCase):
    """A CLI numa thread, com prazo (POR-03): se não volta nele, o teste falha depois de soltar o que prende o kit de
    antes — cada FIFO aberto dos dois lados (solta quem lê e quem escreve) e o que estiver em `soltar` (o processo que
    segura um arrendamento, encerrado)."""

    PRAZO = 15

    def fifo(self, caminho: Path) -> Path:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        if caminho.exists() or caminho.is_symlink():
            caminho.unlink()
        os.mkfifo(caminho)
        self.fifos.append(caminho)
        return caminho

    def setUp(self):
        super().setUp()
        self.fifos: list[Path] = []
        self.soltar: list = []

    def sem_travar(self, *args) -> tuple:
        res: dict = {}
        t = threading.Thread(target=lambda: res.update(r=self.kit(*args)), daemon=True)
        inicio = time.monotonic()
        t.start()
        t.join(self.PRAZO)
        travou = t.is_alive()
        while t.is_alive() and time.monotonic() - inicio < self.PRAZO + 60:
            for f in self.fifos:
                for lado in (os.O_WRONLY, os.O_RDONLY):  # revisão 1: o acréscimo parado no FIFO espera quem leia
                    try:
                        os.close(os.open(f, lado | os.O_NONBLOCK))
                    except OSError:
                        pass
            for soltar in self.soltar:
                soltar()
            t.join(0.5)
        self.assertFalse(travou, f"o kit ficou parado por mais de {self.PRAZO} s: {args}")
        return res["r"]


@unittest.skipUnless(FIFO, "FIFO só no POSIX")
class TestFifoNaoTravaOKit(NaoTravaCase):
    """POR-03: o FIFO é recusado na hora; o kit de antes ficava parado na abertura até alguém escrever nele."""

    def test_registro_trocado_por_fifo_depois_da_conferencia_no_acrescimo(self):
        # Revisão 1: entre o lstat de Pasta.anexar e a abertura, o registro vira um FIFO (a corrida do POR-01, com
        # renameat2). A primeira correção abria o acréscimo esperando um leitor, com a vez do banco na mão; agora,
        # sem leitor, ENXIO e recusa na hora, e nada é gravado.
        from fundacao.core import disco_projeto
        arq = self.preparada()
        self.chaves.assinar(arq)  # aceite válido, ainda sem a linha no registro: o registrar chega ao acréscimo
        reg = self.pasta / "decisoes" / decisoes.REGISTRO
        reg.write_bytes(b"")  # existe: o acréscimo abre o arquivo conferido, sem O_CREAT
        guardado, original, feito = reg.with_name("registro.original"), disco_projeto.Pasta.lstat, []

        def duble(pasta, nome):
            visto = original(pasta, nome)
            if nome == decisoes.REGISTRO and not feito:
                feito.append(reg.rename(guardado))
                self.fifo(reg)
            return visto
        with mock.patch.object(disco_projeto.Pasta, "lstat", duble):
            codigo, r, erro = self.sem_travar("decisao", "registrar", "--arquivo", str(arq))
        self.assertTrue(feito, "a troca não aconteceu: o teste não chegou ao acréscimo")
        self.assertEqual(codigo, 2, (r, erro))
        self.assertIn("E_PATH_ESCAPE", erro)
        self.assertEqual(guardado.read_bytes(), b"")

    def test_decisao_que_e_fifo(self):
        fifo = self.fifo(self.pasta / "decisoes" / "fifo-ficticio.json")
        for args in (("decisao", "verificar", "--arquivo"), ("decisao", "comando", "--arquivo"),
                     ("decisao", "registrar", "--arquivo"), ("tarefa", "concluir", "--decisao")):
            with self.subTest(args=args):
                codigo, r, erro = self.sem_travar(*args, str(fifo))
                self.assertIn(codigo, (2, 3), (r, erro))

    def test_assinatura_registro_e_entrega_que_sao_fifo(self):
        arq = self.preparada()
        self.fifo(Path(str(arq) + ".sig"))
        self.assertEqual(self.sem_travar("decisao", "verificar", "--arquivo", str(arq))[0], 3)
        Path(str(arq) + ".sig").unlink()
        self.chaves.assinar(arq)
        self.fifo(self.pasta / "decisoes" / "registro.jsonl")
        self.assertIn(self.sem_travar("decisao", "registrar", "--arquivo", str(arq))[0], (2, 3))
        self.assertIn(self.sem_travar("tarefa", "concluir", "--decisao", str(arq))[0], (2, 3))
        self.fifo(self.pasta / "outputs" / "entrega.md")
        self.assertEqual(self.sem_travar("decisao", "verificar", "--arquivo", str(arq))[0], 3)
        self.assertEqual(self.sem_travar("decisao", "preparar", "--projeto", "juridico-lab", "--tarefa", self.tarefa,
                                         "--entrega", "outputs/entrega.md", "--tipo", "aceite", "--motivo",
                                         "Aceito.")[0], 2)

    def test_saida_da_etapa_do_aceite_que_e_fifo_na_conclusao_repetida(self):
        arq = self.aceite_registrado()
        codigo, r, erro = self.kit("tarefa", "concluir", "--decisao", str(arq))
        self.assertEqual(codigo, 0, (r, erro))
        saidas = sorted((self.pasta / "outputs" / "runs" / r["run_id"]).glob("*.out"))
        self.assertEqual(len(saidas), 1, saidas)
        self.fifo(saidas[0])
        codigo, de_novo, erro = self.sem_travar("tarefa", "concluir", "--decisao", str(arq))
        # A saída trocada invalida a etapa (A04) e, com uma tentativa só, a execução fica falha: código 3, na hora.
        self.assertEqual((codigo, de_novo and de_novo.get("run_id")), (3, r["run_id"]), (de_novo, erro))


@unittest.skipUnless(ARRENDAMENTO, "arrendamento de arquivo (F_SETLEASE) só no Linux")
class TestArrendamentoNaoTravaOKit(NaoTravaCase):
    """Revisão 1 (POR-03, sem corrida): outro processo do mesmo usuário põe um arrendamento num arquivo do projeto; a
    abertura que conflita esperava até o lease-break-time (45 s) com a vez do banco na mão. Agora recusa na hora."""

    def arrendar(self, caminho: Path, tipo: str) -> None:
        proc = subprocess.Popen([sys.executable, "-I", "-c", SEGURAR_ARRENDAMENTO, str(caminho), tipo],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

        def encerrar():
            if proc.poll() is None:
                proc.kill()
            proc.wait(10)
        self.addCleanup(lambda: (encerrar(), proc.stdin.close(), proc.stdout.close()))
        linha = proc.stdout.readline().strip()
        if linha != "pronto":  # o sistema de arquivos recusa (no DrvFs, EINVAL): não há o que medir
            self.skipTest(f"arrendamento indisponível aqui ({linha or proc.wait(10)})")
        self.soltar.append(encerrar)

    def test_registrar_com_o_registro_arrendado_para_leitura(self):
        # O acréscimo (O_WRONLY) conflita com o arrendamento de leitura: recusa, e a linha não entra.
        arq = self.preparada()
        self.chaves.assinar(arq)
        reg = self.pasta / "decisoes" / decisoes.REGISTRO
        reg.write_bytes(b"")
        self.arrendar(reg, "leitura")
        codigo, r, erro = self.sem_travar("decisao", "registrar", "--arquivo", str(arq))
        self.assertEqual(codigo, 2, (r, erro))
        self.assertIn("E_PATH_ESCAPE", erro)
        self.assertEqual(reg.read_bytes(), b"")

    def test_concluir_com_o_registro_arrendado_para_escrita(self):
        # A leitura do registro (O_RDONLY) conflita com o arrendamento de escrita: recusa, e a tarefa não conclui.
        arq = self.aceite_registrado()
        reg = self.pasta / "decisoes" / decisoes.REGISTRO
        self.arrendar(reg, "escrita")
        codigo, r, erro = self.sem_travar("tarefa", "concluir", "--decisao", str(arq))
        self.assertEqual((codigo, r), (2, None), erro)
        self.assertIn("E_PATH_ESCAPE", erro)
        estado = self.con.execute("SELECT state FROM task WHERE task_id = ?", (self.tarefa,)).fetchone()[0]
        self.assertNotEqual(estado, "succeeded")


class TestRegistroNoTempoDaVez(KitdecCase):
    """Revisão 1 (POR-03): o registro é analisado com a vez do banco na mão. Acima do teto de linhas (as quebras \\n e
    \\r, contadas antes) ou de bytes, recusa sem analisar nenhuma linha; no teto, analisa (meio segundo no pior caso
    medido em ext4). Antes: até 64 MiB, linha por linha (64 MiB de linhas "{}", cerca de 78 s de CPU pela revisão)."""

    def setUp(self):
        super().setUp()
        self.reg = self.pasta / "decisoes" / decisoes.REGISTRO

    def test_acima_do_teto_de_linhas_nenhuma_linha_e_analisada(self):
        for quebra in (b"\n", b"\r"):
            with self.subTest(quebra=quebra), mock.patch.object(decisoes.json, "loads", wraps=json.loads) as analise:
                with self.assertRaises(decisoes.DecisaoInvalida):
                    decisoes.ler_registro(self.reg, (b"{}" + quebra) * (TETO_LINHAS + 1))
                self.assertEqual(analise.call_count, 0)
        self.assertEqual(len(decisoes.ler_registro(self.reg, b"{}\n" * TETO_LINHAS)), TETO_LINHAS)

    def test_concluir_e_registrar_recusam_o_registro_acima_do_teto_de_linhas(self):
        arq = self.aceite_registrado()
        with open(self.reg, "ab") as f:  # depois da linha do aceite: objetos válidos, uma quebra além do teto
            f.write(b"{}\n" * TETO_LINHAS)
        for args in (("tarefa", "concluir", "--decisao", str(arq)), ("decisao", "registrar", "--arquivo", str(arq))):
            with self.subTest(args=args[:2]), mock.patch.object(decisoes.json, "loads", wraps=json.loads) as analise:
                codigo, r, erro = self.kit(*args)
                self.assertEqual((codigo, r), (2, None), erro)
                self.assertIn("E_VALIDATION", erro)
                self.assertLess(analise.call_count, 100, "o registro foi analisado linha por linha")
        self.assertNotEqual(self.con.execute("SELECT state FROM task WHERE task_id = ?", (self.tarefa,)).fetchone()[0],
                            "succeeded")

    def test_registro_acima_do_teto_de_bytes_e_recusado_sem_ler(self):
        arq = self.aceite_registrado()
        linha = json.loads(self.reg.read_bytes())
        outra = json.dumps({**linha, "task_id": "tarefa-ficticia-de-outro-fluxo"}, sort_keys=True).encode() + b"\n"
        with open(self.reg, "ab") as f:  # linhas válidas de outra tarefa, abaixo do teto de linhas e acima do de bytes
            f.write(outra * (TETO_BYTES // len(outra) + 1))
        self.assertLess(self.reg.read_bytes().count(b"\n"), TETO_LINHAS)
        codigo, r, erro = self.kit("tarefa", "concluir", "--decisao", str(arq))
        self.assertEqual((codigo, r), (2, None), erro)
        self.assertIn("E_PATH_ESCAPE", erro)


if __name__ == "__main__":
    unittest.main()
