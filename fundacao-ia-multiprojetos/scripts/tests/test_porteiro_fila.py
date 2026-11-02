"""Porteiro em funcionamento (assets/host/wsl/porteiro.py, 1.7.10; contratos do lote 2, §4), com fila temporária e um
kit fictício que registra cada execução: pedido válido pelo cliente do kit, com o ambiente mínimo e o Python isolado;
pedido por ligação, vínculo físico, FIFO, acima de 64 KiB, pasta e id inválido, recusados sem executar; operação fora
da lista ("1.7.11"), subcomando proibido, --raiz, --ancora e abreviação; aperto de mão que falha (kit sem trava ou
versão menor); árvore do kit e porteiro.json alterados entre pedidos; marcador do Windows; lançador que morre; prazo e
teto de saída; a trava do banco entre dois porteiros e o marcador lido pelo kit. Da revisão do lote 2: o pedido que
espera a vez de outro porteiro segue com sinal de vida e roda uma vez; a vez estourada no aperto de mão não vira recusa
da sessão; texto fora do UTF-8 e exceção inesperada não derrubam o porteiro; o kit roda de uma cópia privada (a troca
na raiz depois da conferência não chega à execução); o pedido que o cliente tirou da fila não roda; pid do lançador
inválido. Da correção do lote 2: o pedido mais velho que a idade máxima não roda (também o que passa dela esperando a
vez, conferido de novo com a vez na mão); quem tira o nome da fila primeiro decide também quando a leitura falha, e o
nome que não sai não roda; um porteiro por projeto (o segundo não apaga as respostas do primeiro) e as pastas de
trabalho de um porteiro morto saem; o aviso da recusa passageira; `eventos` e `memoria licao historico` viram recusa
(emenda E2). Da reconferência 3: a pasta de trabalho em uso (um processo filho com a pasta atual nela ou que a cita
num argumento; o kit órfão de um porteiro morto por SIGKILL) fica, com aviso, e sai na partida seguinte, sem quem a
usa. Só no Linux (descritor de pasta, O_NOFOLLOW, flock, grupo de processos e /proc): no Windows, o equivalente
possível está em test_porteiro.py."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from apoio import KIT

from test_porteiro import PORTEIRO, carregar, kit_ficticio

if str(KIT) not in sys.path:
    sys.path.insert(0, str(KIT))
from fundacao import porteiro_cliente  # noqa: E402
from fundacao.core import trava_banco  # noqa: E402

LINUX = os.name == "posix" and hasattr(os, "killpg") and os.open in os.supports_dir_fd
IDENTIDADE = "FUNDACAO_" + "PRINCIPAL"
ID = "0123456789abcdef0123456789abcdef"
KIT_PRINCIPAL = '''import json, os, sys, time
from pathlib import Path
from . import KIT_VERSION
MODO = "{modo}"


def main(argv):
    resto = argv[2:] if argv[:1] == ["--raiz"] else list(argv)
    registro = {{"argv": list(argv), "env": dict(os.environ), "cwd": os.getcwd(), "path": list(sys.path),
                "isolado": sys.flags.isolated, "sem_site": sys.flags.no_site,
                "sem_bytecode": sys.flags.dont_write_bytecode, "utf8": sys.flags.utf8_mode,
                "pycache_prefix": sys.pycache_prefix, "arquivo": __file__, "modo": MODO}}
    # o porteiro roda uma cópia privada do kit (__file__ é o dela, apagada no fim): o registro vai para a raiz
    with open(Path(os.environ["FUNDACAO_RAIZ"]) / "execucoes.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(registro) + "\\n")
    if resto[:1] == ["status"]:
        trava = None if MODO == "sem-trava" else os.environ.get("FUNDACAO_PROJETO_TRAVADO")
        sys.stdout.write(json.dumps({{"identidade": os.environ.get("FUNDACAO_" + "PRINCIPAL"),
                                     "projetos_autorizados": [trava] if trava else [], "projeto_travado": trava,
                                     "kit_version": KIT_VERSION}}) + "\\n")
        return 0
    if resto[:1] == ["dormir"]:
        time.sleep(float(resto[1]))
        return 0
    if resto[:1] == ["falar"]:
        sys.stdout.write("x" * int(resto[1]))
        return 0
    sys.stdout.write(json.dumps({{"recebido": resto}}, ensure_ascii=False) + "\\n")
    sys.stderr.write("aviso do kit ficticio\\n")
    return 0
'''


# Um porteiro em processo próprio que roda um pedido lento do kit fictício (a sonda da reconferência 3 do lote 2): morto
# por SIGKILL, o kit segue vivo, órfão, em sessão própria, com a pasta atual na pasta de trabalho desse porteiro.
PORTEIRO_LENTO = "\n".join((
    "import importlib.util, os, sys",
    "spec = importlib.util.spec_from_file_location('porteiro_lento', sys.argv[1])",
    "mod = importlib.util.module_from_spec(spec)",
    "spec.loader.exec_module(mod)",
    "p = mod.Porteiro(sys.argv[2], sys.argv[3], os.getpid())",
    "p.abrir()",
    "p.rodar(['dormir', '60'])",
))


def _iso(delta: timedelta = timedelta(0)) -> str:
    return (datetime.now(timezone.utc) + delta).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _pids_dentro(pasta: Path, *, pelos_argumentos: bool = False) -> list[int]:
    """Os processos com a pasta atual dentro de `pasta`, pelo /proc; com `pelos_argumentos`, também os que a citam num
    argumento (o kit órfão mesmo depois de a pasta sair, quando a pasta atual dele vira "(deleted)")."""
    alvo = os.path.realpath(pasta) + os.sep
    pids = []
    for nome in os.listdir("/proc"):
        if not nome.isdigit() or int(nome) == os.getpid():
            continue
        try:
            dentro = (os.readlink(f"/proc/{nome}/cwd") + os.sep).startswith(alvo)
        except OSError:
            dentro = False
        if not dentro and pelos_argumentos:
            try:
                with open(f"/proc/{nome}/cmdline", "rb") as arq:
                    dentro = any(alvo in a.decode("utf-8", "replace") + os.sep for a in arq.read().split(b"\0"))
            except OSError:
                pass
        if dentro:
            pids.append(int(nome))
    return pids


def _encerrar(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.kill()
    proc.wait(10)


def _encerrar_quem_usa(pasta: Path) -> None:
    for pid in _pids_dentro(pasta, pelos_argumentos=True):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


@unittest.skipUnless(LINUX, "fila por descritor de pasta, flock e grupo de processos: só no Linux")
class FilaCase(unittest.TestCase):
    modo, versao = "com-trava", "1.7.10"

    def setUp(self):
        self.mod = carregar()
        self.base = Path(tempfile.mkdtemp(prefix="porteiro-fila-1710-"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.raiz = self.base / "raiz"
        kit_ficticio(self.raiz, self.versao, KIT_PRINCIPAL.format(modo=self.modo))
        (self.raiz / "state").mkdir()
        self.proj = self.raiz / "projects" / "proj-a"
        (self.proj / "decisoes").mkdir(parents=True)
        (self.raiz / "projects" / "proj-b").mkdir()
        self.fila = self.proj / ".porteiro"
        self.casa = self.base / "casa"
        self.casa.mkdir()
        self.config = self.gravar_config()
        self.proc = None

    def gravar_config(self, **mudar) -> Path:
        cfg = {"schema_version": "fundacao.porteiro/1", "raiz": str(self.raiz), "projeto": "proj-a",
               "kit_sha256": self.mod.sha256_do_kit(self.raiz), "assinante": "titular-ficticio",
               "operacoes": {"fundacao": {}}, **mudar}
        arq = self.base / "etc" / "porteiro.json"
        arq.parent.mkdir(exist_ok=True)
        arq.write_text(json.dumps(cfg), encoding="utf-8")
        return arq

    def iniciar(self, pid: int | None = None, fila: Path | None = None, esperar: bool = True):
        env = {"HOME": str(self.casa), "PATH": "/usr/bin:/bin"}
        self.saida_porteiro = self.base / "porteiro.err"
        with open(self.saida_porteiro, "w", encoding="utf-8") as erros:
            self.proc = subprocess.Popen([sys.executable, "-I", "-B", str(PORTEIRO), "servir", "--config",
                                          str(self.config), "--fila", str(fila or self.fila), "--pid-lancador",
                                          str(pid or os.getpid())], env=env, stdout=subprocess.DEVNULL,
                                         stderr=erros)
        self.addCleanup(self.parar)
        if esperar:  # até o primeiro aperto de mão terminar (o sinal de vida sai de "iniciando")
            vida = self.fila / "respostas" / porteiro_cliente.VIDA
            limite = time.monotonic() + 20
            while self.proc.poll() is None and time.monotonic() < limite:
                try:
                    if json.loads(vida.read_text(encoding="utf-8"))["estado"] != "iniciando":
                        return
                except (OSError, ValueError, KeyError):
                    pass
                time.sleep(0.05)
            self.fail("o porteiro não ficou de pé: " + self.saida_porteiro.read_text(encoding="utf-8"))

    def parar(self) -> int | None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            self.proc.wait(20)
        return self.proc.returncode if self.proc is not None else None

    def pedir(self, argv: list[str]) -> dict:
        return porteiro_cliente.pedir(self.fila, argv, prazo=60)

    def esperar_resposta(self, ident: str, prazo: float = 20) -> dict | None:
        arq = self.fila / "respostas" / f"{ident}.json"
        limite = time.monotonic() + prazo
        while time.monotonic() < limite:
            if arq.exists():
                return json.loads(arq.read_text(encoding="utf-8"))
            time.sleep(0.05)
        return None

    def pedido_bruto(self, ident: str = ID, **mudar) -> bytes:
        return json.dumps({"versao": 1, "id": ident, "op": "fundacao", "argv": ["status"], "criado_em": _iso(),
                           **mudar}).encode("utf-8")

    def execucoes(self) -> list[dict]:
        arq = self.raiz / "execucoes.jsonl"
        return [json.loads(l) for l in arq.read_text(encoding="utf-8").splitlines()] if arq.exists() else []

    def registro(self) -> list[dict]:
        arq = self.casa / ".fundacao" / "porteiro" / "proj-a" / "registro.jsonl"
        return [json.loads(l) for l in arq.read_text(encoding="utf-8").splitlines()] if arq.exists() else []

    def mensagem(self, resposta: dict) -> str:
        return json.loads(resposta["stderr"].strip().splitlines()[-1])["error"]["message"]

    def porteiro_aqui(self):
        """Um porteiro neste processo, com as pastas privadas na casa de ensaio, para as partes que o subprocesso não
        expõe (aperto de mão, processar um pedido)."""
        with mock.patch.dict(os.environ, {"HOME": str(self.casa)}):
            p = self.mod.Porteiro(str(self.config), str(self.fila), os.getpid())
            p.abrir()
        self.addCleanup(p.encerrar)
        return p


class TestPedidoValido(FilaCase):
    def test_pedido_valido_ambiente_minimo_python_isolado_e_trava_do_banco(self):
        self.iniciar()
        marcador = json.loads((self.raiz / "state" / trava_banco.MARCADOR).read_text(encoding="utf-8"))
        self.assertEqual((marcador["lado"], marcador["pid"]), ("ubuntu", self.proc.pid))
        r = self.pedir(["tarefa", "criar", "--projeto", "proj-a", "--objetivo", "texto fictício -x"])
        self.assertEqual(r["codigo"], 0, r["stderr"])
        self.assertEqual(json.loads(r["stdout"])["recebido"],
                         ["tarefa", "criar", "--projeto=proj-a", "--objetivo=texto fictício -x"])
        self.assertIn("aviso do kit ficticio", r["stderr"])
        ex = self.execucoes()[-1]
        self.assertEqual(ex["argv"][:2], ["--raiz", str(self.raiz)])
        self.assertEqual(set(ex["env"]) - {"LC_CTYPE"}, {"FUNDACAO_RAIZ", IDENTIDADE, "FUNDACAO_PROJETO_TRAVADO",
                                                          "FUNDACAO_PORTEIRO_SERVIDOR", "FUNDACAO_ASSINANTE", "PATH"}
                         | ({"WSL_DISTRO_NAME"} if "WSL_DISTRO_NAME" in ex["env"] else set()))
        self.assertEqual((ex["env"][IDENTIDADE], ex["env"]["FUNDACAO_PROJETO_TRAVADO"]), ("sessao-proj-a", "proj-a"))
        self.assertEqual((ex["isolado"], ex["sem_site"], ex["sem_bytecode"], ex["utf8"]), (1, 1, 1, 1))
        privada = str(self.casa / ".fundacao" / "porteiro" / "proj-a")
        self.assertTrue(ex["pycache_prefix"].startswith(privada) and ex["cwd"].startswith(privada), ex["cwd"])
        self.assertFalse(any(str(self.raiz) in p for p in ex["path"]), "nada da raiz no caminho de importação")
        [linha] = self.registro()
        self.assertEqual(set(linha), {"id", "op", "codigo", "duracao_s", "em"})
        self.assertEqual((linha["op"], linha["codigo"]), ("fundacao", 0))
        self.assertNotIn("fictício", (self.casa / ".fundacao" / "porteiro" / "proj-a" / "registro.jsonl").read_text(
            encoding="utf-8"), "o registro não leva conteúdo")
        self.assertEqual(self.parar(), 0)
        self.assertFalse((self.raiz / "state" / trava_banco.MARCADOR).exists(), "a trava sai com o porteiro")
        self.assertFalse((self.fila / "respostas" / porteiro_cliente.VIDA).exists())

    def test_status_pelo_cliente_mostra_a_trava(self):
        self.iniciar()
        st = json.loads(self.pedir(["status"])["stdout"])
        self.assertEqual((st["projeto_travado"], st["identidade"]), ("proj-a", "sessao-proj-a"))

    def test_respostas_ficam_so_com_o_porteiro_e_saem_no_fim(self):
        self.iniciar()
        r = self.pedir(["status"])
        self.assertTrue((self.fila / "respostas" / f"{r['id']}.json").exists())
        self.parar()
        self.assertEqual([p.name for p in (self.fila / "respostas").iterdir()], [])


class TestPedidosHostis(FilaCase):
    def test_ligacao_vinculo_fifo_grande_e_pasta_recusados_sem_executar(self):
        self.iniciar()
        antes = len(self.execucoes())
        fora = self.base / "pedido-de-fora.json"
        casos = {}
        for n, (nome, trecho) in enumerate((("ligacao", "ligação"), ("vinculo", "vínculo físico"),
                                            ("fifo", "não é arquivo comum"), ("grande", "teto"),
                                            ("pasta", "não é arquivo comum"))):
            ident = f"{n:032x}"
            destino = self.fila / "pedidos" / f"{ident}.json"
            if nome == "ligacao":
                fora.write_bytes(self.pedido_bruto(ident))
                os.symlink(fora, destino)
            elif nome == "vinculo":
                outro = self.base / f"vinculo-{n}.json"
                outro.write_bytes(self.pedido_bruto(ident))
                os.link(outro, destino)
            elif nome == "fifo":
                os.mkfifo(destino)
            elif nome == "grande":
                destino.write_bytes(self.pedido_bruto(ident, criado_em=_iso())[:-1] + b" " * 70000 + b"}")
            else:
                destino.mkdir()
            casos[nome] = (ident, trecho)
        for nome, (ident, trecho) in casos.items():
            with self.subTest(caso=nome):
                r = self.esperar_resposta(ident)
                self.assertIsNotNone(r, nome)
                self.assertEqual(r["codigo"], 2)
                self.assertIn(trecho, self.mensagem(r))
        self.assertEqual(len(self.execucoes()), antes, "nenhum pedido hostil chegou ao kit")
        self.assertEqual(self.pedir(["status"])["codigo"], 0, "o porteiro segue atendendo (o FIFO não o travou)")
        self.assertEqual(sorted(p.name for p in (self.fila / "pedidos").iterdir()), [], "tudo saiu da fila")

    def test_id_invalido_e_operacao_fora_da_lista(self):
        self.iniciar()
        antes = len(self.execucoes())
        (self.fila / "pedidos" / f"{ID.upper()}.json").write_bytes(self.pedido_bruto(ID.upper()))
        outro = "f" * 32
        (self.fila / "pedidos" / f"{outro}.json").write_bytes(self.pedido_bruto(ID))  # id do conteúdo diferente
        r = self.esperar_resposta(outro)
        self.assertEqual(r["codigo"], 2)
        self.assertIn("id do pedido", self.mensagem(r))
        for n, (op, trecho) in enumerate((("git-enviar", "1.7.11"), ("executar", "1.7.11"), ("rodar", "1.7.11"),
                                          ("outra", "desconhecida"))):
            ident = f"a{n:031x}"
            (self.fila / "pedidos" / f"{ident}.json").write_bytes(self.pedido_bruto(ident, op=op))
            r = self.esperar_resposta(ident)
            with self.subTest(op=op):
                self.assertEqual(r["codigo"], 2)
                self.assertIn(trecho, self.mensagem(r))
        self.assertFalse((self.fila / "pedidos" / f"{ID.upper()}.json").exists(), "nome fora da forma sai da fila")
        self.assertFalse((self.fila / "respostas" / f"{ID.upper()}.json").exists())
        self.assertEqual(len(self.execucoes()), antes)
        ops = [linha["op"] for linha in self.registro()]
        self.assertIn(None, ops)
        self.assertIn("desconhecida", ops)
        self.assertIn("git-enviar", ops)

    def test_subcomando_proibido_raiz_ancora_abreviacao_e_caminho_fora(self):
        self.iniciar()
        antes = len(self.execucoes())
        casos = [["init", "--admin", "x"], ["acl", "registrar", "--principal", "x"],
                 ["backup", "criar", "--destino", "/tmp/x"], ["memoria", "licao", "aprovar", "--memoria", "m",
                                                              "--hash", "h"],
                 ["--raiz", str(self.raiz), "status"], ["status", "--ancora", "a"],
                 ["tarefa", "criar", "--proj", "proj-a"], ["tarefa", "criar", "--projeto", "proj-b", "--objetivo", "x"],
                 ["decisao", "verificar", "--arquivo", str(self.base / "pedido-de-fora.json")],
                 ["decisao", "verificar", "--arquivo", "../proj-b/x.json"]]
        for argv in casos:
            with self.subTest(argv=argv):
                r = self.pedir(argv)
                self.assertEqual(r["codigo"], 2, r)
                self.assertEqual(json.loads(r["stderr"])["error"]["code"], "E_PORTEIRO")
        self.assertEqual(len(self.execucoes()), antes)


class TestConferenciasEntrePedidos(FilaCase):
    def test_arvore_do_kit_alterada_entre_pedidos(self):
        self.iniciar()
        self.assertEqual(self.pedir(["status"])["codigo"], 0)
        antes = len(self.execucoes())
        with open(self.raiz / "fundacao" / "__main__.py", "a", encoding="utf-8") as f:
            f.write("# alterado por uma sessão do Windows\n")
        r = self.pedir(["status"])
        self.assertEqual(r["codigo"], 2)
        self.assertIn("árvore do kit", self.mensagem(r))
        self.assertEqual(len(self.execucoes()), antes, "código não conferido não roda")

    def test_porteiro_json_alterado_entre_pedidos(self):
        self.iniciar()
        self.assertEqual(self.pedir(["status"])["codigo"], 0)
        texto = self.config.read_text(encoding="utf-8")
        self.config.write_text(texto + "\n", encoding="utf-8")
        r = self.pedir(["status"])
        self.assertEqual(r["codigo"], 2)
        self.assertIn("porteiro.json mudou", self.mensagem(r))

    def test_marcador_do_windows_recusa_ate_sair(self):
        marcador = self.raiz / "state" / trava_banco.MARCADOR
        dados = {"lado": "windows", "host": "pc-ficticio", "pid": 77, "desde": _iso(), "renovada_em": _iso()}
        marcador.write_text(json.dumps(dados), encoding="utf-8")
        self.iniciar()
        r = self.pedir(["status"])
        self.assertEqual(r["codigo"], 2)
        self.assertIn("em uso pelo windows", self.mensagem(r))
        self.assertEqual(json.loads(marcador.read_text(encoding="utf-8")), dados, "o marcador do Windows fica")
        marcador.unlink()
        self.assertEqual(self.pedir(["status"])["codigo"], 0)
        self.assertEqual(json.loads(marcador.read_text(encoding="utf-8"))["lado"], "ubuntu")


class TestAvisoSemTrava(FilaCase):
    modo = "sem-trava"

    def test_kit_sem_trava_faz_recusar_todo_pedido_e_solta_o_banco(self):
        self.iniciar()
        for argv in (["status"], ["tarefa", "ver", "--projeto", "proj-a", "--id", "t"]):
            r = self.pedir(argv)
            self.assertEqual(r["codigo"], 2)
            self.assertIn("o kit da raiz não prova a trava", self.mensagem(r))
        self.assertEqual(len(self.execucoes()), 1, "só o status do aperto de mão rodou")
        self.assertFalse((self.raiz / "state" / trava_banco.MARCADOR).exists(), "sem o aperto, o banco fica solto")

    def test_aperto_que_falha_avisa_recusando(self):
        self.iniciar()
        self.assertIn("W_PORTEIRO_RECUSANDO", self.saida_porteiro.read_text(encoding="utf-8"))


class TestAvisoVersaoAntiga(FilaCase):
    versao = "1.7.9"

    def test_kit_anterior_a_1710_faz_recusar(self):
        self.iniciar()
        r = self.pedir(["status"])
        self.assertEqual(r["codigo"], 2)
        self.assertIn("1.7.10", self.mensagem(r))


class TestCicloDeVida(FilaCase):
    def test_lancador_que_morre_encerra_o_porteiro_e_solta_a_trava(self):
        lancador = subprocess.Popen(["sleep", "60"])
        self.addCleanup(lancador.kill)
        self.iniciar(pid=lancador.pid)
        self.assertTrue((self.raiz / "state" / trava_banco.MARCADOR).exists())
        lancador.kill()
        lancador.wait()
        self.assertEqual(self.proc.wait(20), 0)
        self.assertFalse((self.raiz / "state" / trava_banco.MARCADOR).exists())

    def test_respostas_que_e_ligacao_impede_a_partida(self):
        outra = self.base / "outra"
        outra.mkdir()
        (self.fila / "pedidos").mkdir(parents=True)
        os.symlink(outra, self.fila / "respostas")
        self.iniciar(esperar=False)
        self.assertEqual(self.proc.wait(20), 2)
        self.assertEqual(list(outra.iterdir()), [])
        self.assertFalse((self.raiz / "state" / trava_banco.MARCADOR).exists())

    def test_fila_de_outro_projeto_recusada(self):
        self.iniciar(fila=self.raiz / "projects" / "proj-b" / ".porteiro", esperar=False)
        self.assertEqual(self.proc.wait(20), 2)
        self.assertFalse((self.raiz / "projects" / "proj-b" / ".porteiro").exists())


class TestExecucaoEPartes(FilaCase):
    def cfg(self) -> dict:
        return json.loads(self.config.read_text(encoding="utf-8"))

    def test_prazo_e_teto_valem_para_o_kit(self):
        trabalho = tempfile.mkdtemp(dir=self.base)
        r = self.mod.executar_kit(self.cfg(), ["dormir", "30"], pasta_trabalho=trabalho, prazo=1)
        self.assertEqual(r["codigo"], 2)
        self.assertIn("prazo", r["stderr"])
        self.assertLess(r["duracao_s"], 10)
        r = self.mod.executar_kit(self.cfg(), ["falar", "50000"], pasta_trabalho=trabalho, tetos=(1000, 1000))
        self.assertEqual((r["codigo"], r["truncado"], len(r["stdout"])), (2, True, 1000))

    def test_trava_entre_dois_porteiros_e_marcador_lido_pelo_kit(self):
        local = self.casa / "trava"
        local.mkdir()
        a, b = self.mod.TravaDoBanco(str(self.raiz), local), self.mod.TravaDoBanco(str(self.raiz), local)
        estado = self.raiz / "state"
        self.assertIsNone(a.tomar())
        self.assertIsNone(b.tomar())
        with self.assertRaises(trava_banco.BancoTravado):  # o kit do Windows recusa abrir
            trava_banco.conferir(estado, lado="windows")
        trava_banco.conferir(estado, lado="ubuntu")  # o do mesmo lado abre
        self.assertEqual(trava_banco.situacao(trava_banco.ler(estado)), "vivo")
        antes = trava_banco.ler(estado)["renovada_em"]
        time.sleep(0.01)
        self.assertIsNone(a.renovar(forcar=True))
        self.assertNotEqual(trava_banco.ler(estado)["renovada_em"], antes)
        a.soltar()
        self.assertTrue((estado / trava_banco.MARCADOR).exists(), "outro porteiro ainda segura o banco")
        b.soltar()
        self.assertFalse((estado / trava_banco.MARCADOR).exists(), "o último a sair tira o marcador")
        (estado / trava_banco.MARCADOR).write_text(json.dumps(
            {"lado": "windows", "host": "pc", "pid": 1, "desde": _iso(), "renovada_em": _iso()}), encoding="utf-8")
        self.assertIn("windows", a.tomar())
        self.assertFalse(a.segura)

    def test_vez_exclusiva_entre_porteiros(self):
        local = self.casa / "vez"
        local.mkdir()
        a, b = self.mod.TravaDoBanco(str(self.raiz), local), self.mod.TravaDoBanco(str(self.raiz), local)
        with a.na_vez():
            with self.assertRaises(self.mod.Recusa):
                with b.na_vez(espera=0.2):
                    pass
        with b.na_vez(espera=0.2):
            pass


class TestVezDoBanco(FilaCase):
    """Revisão do lote 2: quem espera a vez de outro porteiro segue renovando o sinal de vida, e a vez estourada é
    passageira (não vira recusa da sessão inteira)."""

    def test_pedido_que_espera_a_vez_segue_com_sinal_de_vida_e_roda_uma_vez(self):
        import fcntl
        self.iniciar()
        sem_vida = self.mod.VIDA_S + 1.5          # o cliente desiste com o sinal de vida mais velho que isto
        presa = sem_vida + self.mod.VIDA_S + 1.5  # sem a renovação na espera, o cliente desistiria antes disto
        vez = open(self.mod.TravaDoBanco(str(self.raiz), self.casa / ".fundacao" / "porteiro").vez, "a+b")
        self.addCleanup(vez.close)
        fcntl.flock(vez.fileno(), fcntl.LOCK_EX)  # outro porteiro roda um comando lento
        solta = threading.Timer(presa, vez.close)
        solta.start()
        self.addCleanup(solta.cancel)
        antes, inicio = len(self.execucoes()), time.monotonic()
        r = porteiro_cliente.pedir(self.fila, ["tarefa", "criar", "--projeto", "proj-a", "--objetivo", "fictícia"],
                                   prazo=60, sem_vida=sem_vida)
        self.assertEqual(r["codigo"], 0, r["stderr"])
        self.assertGreaterEqual(time.monotonic() - inicio, presa - 1, "o pedido esperou a vez")
        self.assertEqual(len(self.execucoes()), antes + 1, "rodou uma vez, depois de a vez soltar")

    def test_vez_estourada_no_aperto_de_mao_nao_vira_recusa_permanente(self):
        p = self.porteiro_aqui()
        outra = self.mod.TravaDoBanco(str(self.raiz), p.local)
        with mock.patch.object(self.mod, "ESPERA_VEZ_S", 0.3), outra.na_vez():
            with self.assertRaises(self.mod.VezOcupada):
                p.garantir_pronto()
        p.iniciado = True
        self.assertIsNone(p.recusa_permanente)
        self.assertEqual(p.estado(), "aguardando")
        p.garantir_pronto()  # a vez soltou: o aperto de mão vem no pedido seguinte
        self.assertEqual((p.estado(), p.aperto["projeto_travado"]), ("pronto", "proj-a"))

    def test_espera_da_vez_renova_e_desiste_quando_o_porteiro_encerra(self):
        local = self.casa / "vez"
        local.mkdir()
        a, b = self.mod.TravaDoBanco(str(self.raiz), local), self.mod.TravaDoBanco(str(self.raiz), local)
        chamadas, parar = [], threading.Event()
        with a.na_vez():
            with self.assertRaises(self.mod.VezOcupada):
                with b.na_vez(espera=0.3, durante=lambda: chamadas.append(1)):
                    pass
            self.assertGreater(len(chamadas), 1, "a espera chama `durante` (a trava e o sinal de vida)")
            parar.set()
            inicio = time.monotonic()
            with self.assertRaises(self.mod.Recusa) as ctx:
                with b.na_vez(espera=30, parar=parar):
                    pass
            self.assertLess(time.monotonic() - inicio, 5)
            self.assertNotIsInstance(ctx.exception, self.mod.VezOcupada)
            self.assertIn("encerrando", str(ctx.exception))


class TestPedidoQueNaoDerruba(FilaCase):
    """Revisão do lote 2: texto fora do UTF-8, exceção inesperada e o pedido que o cliente tirou da fila."""

    def test_texto_fora_do_utf8_no_pedido_e_recusado_e_o_porteiro_segue(self):
        self.iniciar()
        antes = len(self.execucoes())
        casos = {"opção": ["tarefa", "criar", "--projeto", "proj-a", "--objetivo", "\ud800"],
                 "caminho": ["decisao", "verificar", "--arquivo", "\ud800"],
                 "comando": ["\udcff"]}
        for n, (nome, argv) in enumerate(casos.items()):
            ident = f"b{n:031x}"
            (self.fila / "pedidos" / f"{ident}.json").write_bytes(self.pedido_bruto(ident, argv=argv))
            r = self.esperar_resposta(ident)
            with self.subTest(caso=nome):
                self.assertIsNotNone(r, "sem resposta: o porteiro caiu?")
                self.assertEqual(r["codigo"], 2)
                self.assertIn("UTF-8", self.mensagem(r))
        self.assertIsNone(self.proc.poll(), "o porteiro segue de pé")
        self.assertEqual(self.pedir(["status"])["codigo"], 0)
        self.assertEqual(len(self.execucoes()), antes + 1, "só o status chegou ao kit")

    def test_excecao_inesperada_vira_resposta(self):
        p = self.porteiro_aqui()
        (self.fila / "pedidos" / f"{ID}.json").write_bytes(self.pedido_bruto())
        with mock.patch.object(p, "atender", side_effect=RuntimeError("defeito simulado")):
            p.processar(f"{ID}.json")
        r = json.loads((self.fila / "respostas" / f"{ID}.json").read_text(encoding="utf-8"))
        self.assertEqual(r["codigo"], 2)
        self.assertIn("erro interno do porteiro (RuntimeError)", self.mensagem(r))
        self.assertEqual(list((self.fila / "pedidos").iterdir()), [])

    def test_pedido_que_o_cliente_tirou_da_fila_nao_roda(self):
        p = self.porteiro_aqui()
        nome = f"{ID}.json"
        (self.fila / "pedidos" / nome).write_bytes(self.pedido_bruto(argv=["tarefa", "criar", "--objetivo", "x"]))
        ler = p.fila.ler

        def ler_e_o_cliente_desiste(n):
            dados = ler(n)
            os.unlink(self.fila / "pedidos" / n)  # o cliente desistiu e tirou o pedido antes de o porteiro tirar
            return dados
        antes = len(self.execucoes())
        with mock.patch.object(p.fila, "ler", side_effect=ler_e_o_cliente_desiste):
            p.processar(nome)
        self.assertEqual(len(self.execucoes()), antes, "quem tira o nome da fila primeiro decide: não rodou")
        self.assertFalse((self.fila / "respostas" / nome).exists())

    def test_pid_do_lancador_zero_recusado_sem_tomar_a_trava(self):
        r = subprocess.run([sys.executable, "-I", "-B", str(PORTEIRO), "servir", "--config", str(self.config),
                            "--fila", str(self.fila), "--pid-lancador", "0"], capture_output=True, text=True,
                           encoding="utf-8", env={"HOME": str(self.casa), "PATH": "/usr/bin:/bin"}, timeout=30)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("pid do lançador inválido", json.loads(r.stderr)["error"]["message"])
        self.assertFalse((self.raiz / "state" / trava_banco.MARCADOR).exists())
        self.assertFalse(self.fila.exists())


class TestCopiaPrivadaDoKit(FilaCase):
    """Revisão do lote 2: o porteiro executa a cópia privada feita no mesmo passe do hash e a apaga no fim."""

    def test_kit_roda_da_copia_privada_e_ela_sai_no_fim(self):
        self.iniciar()
        self.assertEqual(self.pedir(["status"])["codigo"], 0)
        ex = self.execucoes()[-1]
        privada = str(self.casa / ".fundacao" / "porteiro" / "proj-a")
        self.assertTrue(ex["arquivo"].startswith(privada), ex["arquivo"])
        self.assertFalse(ex["arquivo"].startswith(str(self.raiz)))
        self.assertFalse(os.path.exists(ex["arquivo"]), "a cópia sai no fim do pedido")

    def test_troca_no_kit_da_raiz_depois_da_conferencia_nao_chega_a_execucao(self):
        trabalho = tempfile.mkdtemp(dir=self.base)
        principal = self.raiz / "fundacao" / "__main__.py"
        conferir = self.mod.kit_conferido

        def conferir_e_trocar(*args):
            pacote = conferir(*args)  # conferida e copiada: agora alguém troca o arquivo na raiz
            principal.write_text(principal.read_text(encoding="utf-8").replace('MODO = "com-trava"',
                                                                                'MODO = "trocado"'), encoding="utf-8")
            return pacote
        cfg = json.loads(self.config.read_text(encoding="utf-8"))
        with mock.patch.object(self.mod, "kit_conferido", side_effect=conferir_e_trocar):
            r = self.mod.executar_kit(cfg, ["--raiz", str(self.raiz), "status"], pasta_trabalho=trabalho)
        self.assertEqual(r["codigo"], 0, r["stderr"])
        ex = self.execucoes()[-1]
        self.assertEqual(ex["modo"], "com-trava", "rodou a cópia conferida, não o arquivo trocado na raiz")
        self.assertTrue(ex["arquivo"].startswith(trabalho) and not os.path.exists(ex["arquivo"]), ex["arquivo"])
        with self.assertRaises(self.mod.KitAlterado):  # e o pedido seguinte recusa a troca
            self.mod.executar_kit(cfg, ["status"], pasta_trabalho=trabalho)
        self.assertEqual(len(self.execucoes()), 1)
        self.assertEqual(os.listdir(trabalho), [], "nenhuma cópia ficou na pasta de trabalho")


class TestIdadeDoPedido(FilaCase):
    """Correção do lote 2: a espera somada ao prazo do kit cabe no corte de 120 s do Bash; o pedido mais velho que a
    idade máxima não roda (nem o que um cliente morto deixou na fila), a espera da vez para no limite da idade, e a
    idade é conferida de novo com a vez na mão."""

    def pedido_na_fila(self) -> str:
        nome = f"{ID}.json"
        (self.fila / "pedidos" / nome).write_bytes(self.pedido_bruto(argv=["tarefa", "criar", "--objetivo", "x"]))
        return nome

    def resposta(self, nome: str) -> dict:
        return json.loads((self.fila / "respostas" / nome).read_text(encoding="utf-8"))

    def test_pedido_velho_ou_adiantado_nao_roda(self):
        self.iniciar()
        antes = len(self.execucoes())
        for n, (criado_em, trecho) in enumerate(((_iso(-timedelta(hours=1)), "esperou"),
                                                 (_iso(timedelta(minutes=1)), "futuro"))):
            ident = f"c{n:031x}"
            (self.fila / "pedidos" / f"{ident}.json").write_bytes(
                self.pedido_bruto(ident, argv=["tarefa", "criar", "--objetivo", "x"], criado_em=criado_em))
            r = self.esperar_resposta(ident)
            with self.subTest(trecho=trecho):
                self.assertIsNotNone(r)
                self.assertEqual(r["codigo"], 2)
                self.assertIn("não rodou", self.mensagem(r))
                self.assertIn(trecho, self.mensagem(r))
        self.assertEqual(len(self.execucoes()), antes, "nenhum dos dois rodou")
        self.assertEqual(self.pedir(["status"])["codigo"], 0, "o pedido novo roda")

    def test_pedido_que_passa_da_idade_esperando_a_vez_nao_roda(self):
        import fcntl
        p = self.porteiro_aqui()
        p.garantir_pronto()  # o aperto de mão com a vez livre
        vez = open(p.trava.vez, "a+b")
        self.addCleanup(vez.close)
        fcntl.flock(vez.fileno(), fcntl.LOCK_EX)  # outro porteiro roda um comando lento
        solta = threading.Timer(3, vez.close)
        solta.start()
        self.addCleanup(solta.cancel)
        nome, antes, inicio = self.pedido_na_fila(), len(self.execucoes()), time.monotonic()
        with mock.patch.object(self.mod, "IDADE_MAXIMA_S", 1):
            p.processar(nome)
        self.assertLess(time.monotonic() - inicio, 2.5, "a espera parou no limite da idade, antes de a vez soltar")
        r = self.resposta(nome)
        self.assertEqual(r["codigo"], 2)
        self.assertIn("não rodou", self.mensagem(r))
        self.assertEqual(len(self.execucoes()), antes)

    def test_idade_conferida_de_novo_com_a_vez_na_mao(self):
        p = self.porteiro_aqui()
        p.garantir_pronto()
        reler = p.reconferir_config

        def reler_devagar():  # a configuração demora a reler: a idade passa com a vez já na mão
            time.sleep(1.5)
            reler()
        nome, antes = self.pedido_na_fila(), len(self.execucoes())
        with mock.patch.object(self.mod, "IDADE_MAXIMA_S", 1), \
                mock.patch.object(p, "reconferir_config", side_effect=reler_devagar):
            p.processar(nome)
        r = self.resposta(nome)
        self.assertEqual(r["codigo"], 2)
        self.assertIn("não rodou", self.mensagem(r))
        self.assertEqual(len(self.execucoes()), antes)

    def test_copia_conferida_lenta_conta_na_idade_e_o_kit_nao_comeca(self):
        p = self.porteiro_aqui()
        p.garantir_pronto()
        conferir = self.mod.kit_conferido

        def copia_lenta(*args):  # a cópia conferida demora (DrvFs): conta na idade, como a fila e a vez
            time.sleep(1.5)
            return conferir(*args)
        nome, antes = self.pedido_na_fila(), len(self.execucoes())
        with mock.patch.object(self.mod, "IDADE_MAXIMA_S", 1), \
                mock.patch.object(self.mod, "kit_conferido", side_effect=copia_lenta):
            p.processar(nome)
        r = self.resposta(nome)
        self.assertEqual(r["codigo"], 2)
        self.assertIn("não rodou", self.mensagem(r))
        self.assertEqual(len(self.execucoes()), antes, "o kit não começou")
        self.assertEqual(os.listdir(p.trabalho), [], "a cópia não ficou na pasta de trabalho")


class TestQuemTiraPrimeiro(FilaCase):
    """Correção do lote 2: quem tira o nome da fila primeiro decide se o pedido roda, também quando a leitura falha; o
    nome que não sai da fila não roda."""

    def test_leitura_que_falha_depois_de_o_nome_sair_nao_responde(self):
        """Sonda S1: sem isto, a recusa "não abriu" ficava no lugar da resposta de quem tirou o pedido."""
        p = self.porteiro_aqui()
        p.garantir_pronto()
        nome = f"{ID}.json"
        (self.fila / "pedidos" / nome).write_bytes(self.pedido_bruto())
        ler = p.fila.ler

        def o_nome_sai_antes(n):
            os.unlink(self.fila / "pedidos" / n)  # o cliente (ou outro porteiro) tirou o nome antes da leitura
            return ler(n)
        antes = len(self.execucoes())
        with mock.patch.object(p.fila, "ler", side_effect=o_nome_sai_antes):
            p.processar(nome)
        self.assertFalse((self.fila / "respostas" / nome).exists(), "o porteiro gravou uma recusa de pedido alheio")
        self.assertEqual(len(self.execucoes()), antes)

    def test_nome_que_nao_sai_da_fila_nao_roda(self):
        p = self.porteiro_aqui()
        p.garantir_pronto()
        nome = f"{ID}.json"
        (self.fila / "pedidos" / nome).write_bytes(self.pedido_bruto(argv=["tarefa", "criar", "--objetivo", "x"]))
        antes = len(self.execucoes())
        with mock.patch.object(p.fila, "retirar", return_value=False):  # o unlink recusado (no DrvFs, arquivo aberto)
            p.processar(nome)
            p.processar(nome)  # e não é lido de novo nesta sessão
        r = json.loads((self.fila / "respostas" / nome).read_text(encoding="utf-8"))
        self.assertEqual(r["codigo"], 2)
        self.assertIn("não rodou", self.mensagem(r))
        self.assertEqual(len(self.execucoes()), antes, "o pedido que ficou na fila não rodou")
        self.assertIn(nome, p.ignorados)


class TestUmPorteiroPorProjeto(FilaCase):
    """Correção do lote 2 (sonda S6): o segundo porteiro do projeto sai antes de tocar a fila; com a trava na mão, as
    pastas de trabalho de um porteiro morto saem."""

    def test_segundo_porteiro_recusado_sem_apagar_as_respostas_do_primeiro(self):
        self.iniciar()
        r = self.pedir(["status"])
        resposta, vida = self.fila / "respostas" / f"{r['id']}.json", self.fila / "respostas" / porteiro_cliente.VIDA
        segundo = subprocess.run([sys.executable, "-I", "-B", str(PORTEIRO), "servir", "--config", str(self.config),
                                  "--fila", str(self.fila), "--pid-lancador", str(os.getpid())], capture_output=True,
                                 text=True, encoding="utf-8", env={"HOME": str(self.casa), "PATH": "/usr/bin:/bin"},
                                 timeout=30)
        self.assertEqual(segundo.returncode, 2, segundo.stderr)
        self.assertIn("já há um porteiro deste projeto", json.loads(segundo.stderr)["error"]["message"])
        self.assertTrue(resposta.exists(), "a resposta do primeiro ficou")
        self.assertTrue(vida.exists(), "o sinal de vida do primeiro ficou")
        self.assertEqual(self.pedir(["status"])["codigo"], 0, "o primeiro segue atendendo")

    def test_pastas_de_trabalho_de_um_porteiro_morto_saem(self):
        privada = self.casa / ".fundacao" / "porteiro" / "proj-a"
        velha = privada / "trabalho-velho" / "kit-x" / "fundacao"
        velha.mkdir(parents=True)
        (velha / "__init__.py").write_text('KIT_VERSION = "1.7.10"\n', encoding="utf-8")
        fora = self.base / "fora"
        fora.mkdir()
        (fora / "fica.txt").write_text("de fora\n", encoding="utf-8")
        os.symlink(fora, privada / "trabalho-ligado")
        self.iniciar()
        self.assertFalse((privada / "trabalho-velho").exists(), "a cópia do porteiro morto saiu")
        self.assertTrue((fora / "fica.txt").exists(), "a ligação não foi seguida")
        reais = [p.name for p in privada.iterdir() if p.name.startswith("trabalho-") and not p.is_symlink()]
        self.assertEqual(len(reais), 1, reais)

    def filho(self, argv: list[str], cwd: Path) -> subprocess.Popen:
        proc = subprocess.Popen(argv, cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        self.addCleanup(_encerrar, proc)
        return proc

    def test_pasta_de_trabalho_em_uso_fica_e_sai_depois_sem_quem_a_usa(self):
        """Reconferência 3 do lote 2: na partida, a pasta trabalho-* que um processo filho ainda usa — com a pasta atual
        dentro dela ou citando-a num argumento — fica, com o aviso W_PORTEIRO_TRABALHO_MANTIDO, como no limpar-porteiro
        do HOST; a que ninguém usa sai; e as que ficaram saem na partida seguinte, sem quem as usa."""
        privada = self.casa / ".fundacao" / "porteiro" / "proj-a"
        com_cwd, citada, livre = (privada / n for n in ("trabalho-orfao001", "trabalho-citada01", "trabalho-livre001"))
        for pasta in (com_cwd, citada, livre):
            (pasta / "kit-x" / "fundacao").mkdir(parents=True)
        dentro = self.filho(["sleep", "60"], cwd=com_cwd / "kit-x")
        citante = self.filho([sys.executable, "-I", "-c", "import time; time.sleep(60)",
                              str(citada / "kit-x" / "fundacao")], cwd=self.base)
        self.iniciar()
        self.assertTrue((com_cwd / "kit-x").is_dir(), "a pasta com um processo dentro ficou")
        self.assertTrue((citada / "kit-x" / "fundacao").is_dir(), "a pasta citada num argumento ficou")
        self.assertFalse(livre.exists(), "a que ninguém usa saiu")
        aviso = self.saida_porteiro.read_text(encoding="utf-8")
        self.assertIn("W_PORTEIRO_TRABALHO_MANTIDO", aviso)
        self.assertIn(f"trabalho-orfao001 (em uso pelo processo {dentro.pid}", aviso)
        self.assertIn(f"trabalho-citada01 (em uso pelo processo {citante.pid}", aviso)
        self.assertEqual(self.pedir(["status"])["codigo"], 0, "o porteiro segue atendendo")
        self.parar()
        for proc in (dentro, citante):
            _encerrar(proc)
        self.iniciar()
        self.assertFalse(com_cwd.exists(), "sem quem a usava, saiu na partida seguinte")
        self.assertFalse(citada.exists(), "sem quem a citava, saiu na partida seguinte")
        self.assertNotIn("W_PORTEIRO_TRABALHO_MANTIDO", self.saida_porteiro.read_text(encoding="utf-8"))

    def test_kit_orfao_de_um_porteiro_morto_por_sigkill_fica_com_a_pasta(self):
        """A sonda da reconferência 3: um porteiro roda um pedido lento e leva SIGKILL; o kit, em sessão própria, segue
        vivo, órfão, com a pasta atual na pasta de trabalho dele. O `servir` seguinte não a apaga (antes, apagava, e a
        pasta atual do órfão virava "(deleted)")."""
        self.addCleanup(_encerrar_quem_usa, self.casa)  # o kit órfão sai no fim, também se o teste falhar no meio
        lento = subprocess.Popen([sys.executable, "-I", "-B", "-c", PORTEIRO_LENTO, str(PORTEIRO), str(self.config),
                                  str(self.fila)], env={"HOME": str(self.casa), "PATH": "/usr/bin:/bin"},
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(_encerrar, lento)
        limite, dormindo = time.monotonic() + 20, []
        while not dormindo:
            self.assertIsNone(lento.poll(), "o porteiro de ensaio saiu antes de o kit lento começar")
            self.assertLess(time.monotonic(), limite, "o kit lento não começou")
            time.sleep(0.05)
            try:
                dormindo = [e for e in self.execucoes() if e["argv"] == ["dormir", "60"]]
            except ValueError:  # a linha do registro ainda sendo gravada
                pass
        velha = Path(dormindo[0]["cwd"])
        os.kill(lento.pid, signal.SIGKILL)
        lento.wait(10)
        orfaos = _pids_dentro(velha)
        self.assertTrue(orfaos, "o kit órfão segue vivo dentro da pasta de trabalho do porteiro morto")
        self.iniciar()
        self.assertTrue(velha.is_dir(), "a pasta do kit órfão ficou")
        for pid in orfaos:
            self.assertFalse(os.readlink(f"/proc/{pid}/cwd").endswith("(deleted)"), "a pasta atual do órfão existe")
        self.assertIn("W_PORTEIRO_TRABALHO_MANTIDO", self.saida_porteiro.read_text(encoding="utf-8"))
        self.assertEqual(self.pedir(["status"])["codigo"], 0, "o porteiro novo atende")


class TestAvisoEMapa(FilaCase):
    def test_recusa_passageira_no_inicio_avisa_aguardando(self):
        dados = {"lado": "windows", "host": "pc-ficticio", "pid": 77, "desde": _iso(), "renovada_em": _iso()}
        (self.raiz / "state" / trava_banco.MARCADOR).write_text(json.dumps(dados), encoding="utf-8")
        self.iniciar()
        avisos = self.saida_porteiro.read_text(encoding="utf-8")
        self.assertIn("W_PORTEIRO_AGUARDANDO", avisos)
        self.assertNotIn("W_PORTEIRO_RECUSANDO", avisos)

    def test_eventos_e_historico_viram_recusa_sem_executar(self):
        """Emenda E2 dos contratos: fora do mapa na 1.7.10, mesmo com o caminho dentro do projeto."""
        self.iniciar()
        antes = len(self.execucoes())
        for argv in (["eventos", "verificar"], ["eventos", "exportar", "--destino", str(self.proj / "e.jsonl")],
                     ["memoria", "licao", "historico", "--memoria", "m"]):
            with self.subTest(argv=argv):
                r = self.pedir(argv)
                self.assertEqual(r["codigo"], 2, r)
                self.assertEqual(json.loads(r["stderr"])["error"]["code"], "E_PORTEIRO")
                self.assertIn("fora do mapa", self.mensagem(r))
        self.assertEqual(len(self.execucoes()), antes)


if __name__ == "__main__":
    unittest.main()
