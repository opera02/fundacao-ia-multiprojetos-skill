"""Revisão de segurança da 1.7.10, grupo KITDEC, com o porteiro e o kit de verdade numa fundação fictícia em pasta
temporária (no Ubuntu, /tmp, ext4), como o achado mediu. Só no Linux (WSL ou a CI pública).

- POR-01, a sonda da troca atômica: enquanto outro processo troca projects/proj-a/decisoes por uma ligação, em laço
  (renameat2 com RENAME_EXCHANGE), a sessão do proj-a pede `decisao preparar` pela fila várias vezes; nenhuma decisão
  pode aparecer fora de projects/proj-a/ (o achado mediu 9 em 60 com a ligação para o proj-b e criou
  state/manutencao.json na 9ª tentativa). No kit de antes, a sonda acha decisões do proj-a do outro lado da ligação.
- POR-03, dois porteiros na mesma raiz e na mesma casa (a mesma vez do banco): um FIFO em projects/proj-a/decisoes/
  é recusado na hora, e o `status` do proj-b, pedido enquanto o proj-a confere o FIFO, roda dentro da idade máxima do
  pedido. No kit de antes, o kit do proj-a ficava parado no FIFO com a vez na mão, e o do proj-b voltava "o banco está
  ocupado por outro porteiro".
- Revisão 1 do grupo (POR-03), os dois porteiros com uma âncora e uma chave de ENSAIO (a decisão assinada chega ao
  registro): o registro.jsonl do proj-a arrendado por outro processo (F_SETLEASE) em `decisao registrar`, e o registro
  com mais quebras de linha que o teto em `tarefa concluir`, não prendem a vez; o `status` do proj-b roda. Na primeira
  correção, com a vez na mão, o acréscimo esperava o arrendamento (o `status` do proj-b voltou "ocupado" aos 15,2 s) e
  a conclusão analisava o registro inteiro (10,4 s com os 7,5 MB deste teste; o teto era 64 MiB).
Dados e identidades fictícios."""

from __future__ import annotations

import ctypes
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from apoio import ENV, KIT, versao_do_kit

from test_porteiro import PORTEIRO, carregar
from test_porteiro_fila import LINUX

if str(KIT) not in sys.path:
    sys.path.insert(0, str(KIT))
from fundacao import porteiro_cliente  # noqa: E402

IDENTIDADE = "FUNDACAO_" + "PRINCIPAL"
FORA_DO_REGISTRY = {"kit_backup", "kit_preparo", "kit_install.json", "atualizacoes.jsonl", "inventario-host.json",
                    "ultima-copia.json"}
# Troca os dois nomes de uma vez, em laço, até ser encerrado (renameat2 com RENAME_EXCHANGE, como a sonda do achado).
TROCADOR = "\n".join((
    "import ctypes, os, sys",
    "libc = ctypes.CDLL(None, use_errno=True)",
    "trocar = libc.renameat2",
    "trocar.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]",
    "a, b = os.fsencode(sys.argv[1]), os.fsencode(sys.argv[2])",
    "sys.stdout.write('pronto\\n')",
    "sys.stdout.flush()",
    "while trocar(-100, a, -100, b, 2) == 0:",
    "    pass",
    "sys.exit(3)",
))
TENTATIVAS = 24  # por alvo: o kit de antes deixa decisões do outro lado em cerca de 1 de cada 7 (o achado: 9 em 60)
# Segura um arrendamento de leitura (F_SETLEASE) no arquivo até ser encerrado, ignorando o aviso de quebra (SIGIO).
ARRENDADOR = "\n".join((
    "import fcntl, os, signal, sys",
    "signal.signal(signal.SIGIO, signal.SIG_IGN)",
    "fd = os.open(sys.argv[1], os.O_RDONLY)",
    "try:",
    "    fcntl.fcntl(fd, getattr(fcntl, 'F_SETLEASE', 1024), fcntl.F_RDLCK)",
    "except OSError as exc:",
    "    sys.stdout.write(f'indisponivel errno {exc.errno}\\n')",
    "    sys.stdout.flush()",
    "    sys.exit(3)",
    "sys.stdout.write('pronto\\n')",
    "sys.stdout.flush()",
    "sys.stdin.read()",
))
LINHAS_ALEM_DO_TETO = 2_500_000  # linhas "{}" (7,5 MB, abaixo do teto de bytes): o teto de linhas recusa antes
PATH_DO_SISTEMA = "/usr/bin:/bin"


def _renameat2_disponivel() -> bool:
    if os.name != "posix":
        return False
    try:
        return hasattr(ctypes.CDLL(None), "renameat2")
    except (OSError, TypeError):
        return False


@unittest.skipUnless(LINUX, "porteiro: só no Linux")
class PorteirosCase(unittest.TestCase):
    """Uma fundação fictícia com o kit da skill, proj-a e proj-b, e um porteiro por projeto pedido em `porteiros`,
    todos com a mesma casa."""

    porteiros: tuple[str, ...] = ("proj-a",)
    ancora_de_ensaio = False  # revisão 1: a âncora da cópia aponta para uma de ENSAIO, e a chave fica em self.chave

    def setUp(self):
        self.mod = carregar()
        self.base = Path(tempfile.mkdtemp(prefix="porteiro-kitdec-1710-"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.raiz = self.base / "raiz"
        ignorar = shutil.ignore_patterns("__pycache__", "*.pyc")
        shutil.copytree(KIT / "fundacao", self.raiz / "fundacao", ignore=ignorar)
        shutil.copytree(KIT / "registry", self.raiz / "registry",
                        ignore=lambda pasta, nomes: set(ignorar(pasta, nomes)) | (FORA_DO_REGISTRY & set(nomes)))
        shutil.copytree(KIT / "templates", self.raiz / "templates", ignore=ignorar)
        versao = versao_do_kit(self.raiz)
        if tuple(int(n) for n in re.findall(r"\d+", versao)[:3]) < (1, 7, 10):
            init = self.raiz / "fundacao" / "__init__.py"
            init.write_text(init.read_text(encoding="utf-8").replace(f'"{versao}"', '"1.7.10"'), encoding="utf-8")
        decisoes_py = self.raiz / "fundacao" / "core" / "decisoes.py"
        texto = decisoes_py.read_text(encoding="utf-8")
        # A âncora desta máquina fica de fora: a da cópia não existe (ou é a de ENSAIO, com `ancora_de_ensaio`).
        ancoras = {nome: self.base / "sem-ancora" / nome for nome in ("ANCORA_WSL", "ANCORA_POSIX")}
        if self.ancora_de_ensaio:
            ancoras["ANCORA_POSIX"] = self.ancora_e_chave()
        for nome, caminho in ancoras.items():
            texto = re.sub(rf'^{nome} = "[^"]*"', f'{nome} = "{caminho}"', texto, flags=re.M)
        decisoes_py.write_text(texto, encoding="utf-8")
        self.env = {k: v for k, v in ENV.items() if not k.startswith("FUNDACAO_")}
        self.kit("init", "--admin", "titular-ficticio")
        for projeto in ("proj-a", "proj-b"):
            self.kit("projeto", "criar", "--id", projeto, "--nome", f"Projeto {projeto}", "--finalidade",
                     "Ensaio fictício do porteiro")
        self.casa = self.base / "casa"
        self.casa.mkdir()
        self.procs, self.filas = {}, {}
        for projeto in self.porteiros:
            self.servir(projeto)

    def ancora_e_chave(self) -> Path:
        """Chave de ENSAIO sem senha (some com a pasta) e a âncora que só a conhece, para o assinante do porteiro."""
        keygen = shutil.which("ssh-keygen", path=PATH_DO_SISTEMA)
        if not keygen:
            self.skipTest("ssh-keygen do sistema indisponível")
        self.keygen, self.chave = keygen, self.base / "chaves" / "titular-ficticio"
        self.chave.parent.mkdir()
        subprocess.run([keygen, "-q", "-t", "ed25519", "-N", "", "-C", "titular-ficticio", "-f", str(self.chave)],
                       check=True, capture_output=True)
        ancora = self.base / "ancora" / "allowed_signers"
        ancora.parent.mkdir()
        publica = Path(str(self.chave) + ".pub").read_text(encoding="ascii").strip()
        ancora.write_text(f'titular-ficticio namespaces="fundacao-decisao" {publica}\n', encoding="ascii")
        return ancora

    def kit(self, *args) -> dict:
        r = subprocess.run([sys.executable, "-B", "-m", "fundacao", "--raiz", str(self.raiz), *args],
                           capture_output=True, text=True, encoding="utf-8", cwd=str(self.raiz), timeout=120,
                           env={**self.env, IDENTIDADE: "titular-ficticio"})
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def servir(self, projeto: str) -> None:
        cfg = {"schema_version": "fundacao.porteiro/1", "raiz": str(self.raiz), "projeto": projeto,
               "kit_sha256": self.mod.sha256_do_kit(self.raiz), "assinante": "titular-ficticio",
               "operacoes": {"fundacao": {}}}
        config = self.base / "etc" / projeto / "porteiro.json"
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps(cfg), encoding="utf-8")
        fila = self.raiz / "projects" / projeto / ".porteiro"
        with open(self.base / f"porteiro-{projeto}.err", "w", encoding="utf-8") as erros:
            proc = subprocess.Popen([sys.executable, "-I", "-B", str(PORTEIRO), "servir", "--config", str(config),
                                     "--fila", str(fila), "--pid-lancador", str(os.getpid())],
                                    env={"HOME": str(self.casa), "PATH": "/usr/bin:/bin"},
                                    stdout=subprocess.DEVNULL, stderr=erros)
        self.procs[projeto], self.filas[projeto] = proc, fila
        self.addCleanup(self.parar, proc)
        vida, limite = fila / "respostas" / porteiro_cliente.VIDA, time.monotonic() + 60
        while time.monotonic() < limite and proc.poll() is None:
            try:
                if json.loads(vida.read_text(encoding="utf-8"))["estado"] != "iniciando":
                    break
            except (OSError, ValueError, KeyError):
                pass
            time.sleep(0.1)

    @staticmethod
    def parar(proc) -> None:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            proc.wait(30)

    def pedir(self, projeto: str, *argv, prazo: float = 150) -> tuple[int, dict | None, str, float]:
        inicio = time.monotonic()
        r = porteiro_cliente.pedir(self.filas[projeto], list(argv), prazo=prazo)
        saida = json.loads(r["stdout"]) if r["stdout"].strip() else None
        return r["codigo"], saida, r["stderr"], time.monotonic() - inicio

    def tarefa_com_entrega(self) -> str:
        codigo, r, erro, _ = self.pedir("proj-a", "tarefa", "criar", "--projeto", "proj-a", "--objetivo",
                                        "entrega fictícia")
        self.assertEqual(codigo, 0, (erro, (self.base / "porteiro-proj-a.err").read_text(encoding="utf-8")))
        (self.raiz / "projects" / "proj-a" / "outputs" / "entrega.md").write_text("Entrega fictícia.\n",
                                                                                  encoding="utf-8")
        return r["task_id"]


@unittest.skipUnless(_renameat2_disponivel(), "renameat2 indisponível nesta libc")
class TestSondaDaTrocaDeDecisoes(PorteirosCase):
    """POR-01: a sonda de troca atômica de decisoes/ por ligação, em laço, com o kit rodando pelo porteiro."""

    def trocar_em_laco(self, alvo: Path):
        projeto = self.raiz / "projects" / "proj-a"
        ligacao = projeto / "dec-ligacao"
        if ligacao.is_symlink():
            ligacao.unlink()
        ligacao.symlink_to(alvo, target_is_directory=True)
        proc = subprocess.Popen([sys.executable, "-I", "-c", TROCADOR, str(projeto / "decisoes"), str(ligacao)],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        self.assertEqual(proc.stdout.readline().strip(), "pronto")
        return proc, projeto, ligacao

    def parar_troca(self, proc, projeto: Path, ligacao: Path) -> None:
        proc.kill()
        proc.wait(10)
        proc.stdout.close()
        self.assertNotEqual(proc.returncode, 3, "a troca falhou: o sistema de arquivos não troca os dois nomes")
        if (projeto / "decisoes").is_symlink():  # parou com os nomes trocados: a pasta volta ao nome dela
            os.rename(projeto / "decisoes", projeto / "dec-tmp")
            os.rename(ligacao, projeto / "decisoes")
            os.rename(projeto / "dec-tmp", ligacao)
        ligacao.unlink()

    def test_nenhuma_decisao_fora_do_projeto_em_varias_tentativas(self):
        tarefa = self.tarefa_com_entrega()
        (self.raiz / "projects" / "proj-a" / "decisoes").mkdir(exist_ok=True)
        alvos = {"proj-b": self.raiz / "projects" / "proj-b" / "decisoes", "state": self.raiz / "state"}
        alvos["proj-b"].mkdir(exist_ok=True)
        respostas, fora = {}, {}
        for nome, alvo in alvos.items():
            proc, projeto, ligacao = self.trocar_em_laco(alvo)
            try:
                for n in range(TENTATIVAS):
                    codigo, _r, erro, _ = self.pedir(
                        "proj-a", "decisao", "preparar", "--projeto", "proj-a", "--tarefa", tarefa, "--entrega",
                        "outputs/entrega.md", "--tipo", "aceite", "--motivo", "motivo ficticio", "--decisao-id",
                        f"corrida-{nome}-{n}", "--shell", "bash", prazo=60)
                    chave = "codigo0" if codigo == 0 else (re.findall(r'"code": "(\w+)"', erro) or [f"c{codigo}"])[-1]
                    respostas[chave] = respostas.get(chave, 0) + 1
            finally:
                self.parar_troca(proc, projeto, ligacao)
            fora[nome] = sorted(p.name for p in alvo.iterdir() if p.name.startswith("corrida-"))
        dentro = sorted(p.name for p in (self.raiz / "projects" / "proj-a" / "decisoes").iterdir()
                        if p.name.startswith("corrida-"))
        self.sonda = {"respostas": respostas, "fora": {k: len(v) for k, v in fora.items()}, "dentro": len(dentro)}
        self.assertEqual(fora, {"proj-b": [], "state": []}, f"decisões fora de projects/proj-a/: {self.sonda}")
        self.assertTrue(dentro, f"nenhuma tentativa gravou a decisão: a sonda não exercitou a gravação ({respostas})")
        self.assertNotIn("E_PORTEIRO", respostas, respostas)


class TestFifoNaoPrendeAVezDoBanco(PorteirosCase):
    """POR-03: dois porteiros reais na mesma raiz e na mesma casa; o FIFO do proj-a não segura a vez do proj-b."""

    porteiros = ("proj-a", "proj-b")

    def test_status_do_outro_projeto_roda_enquanto_o_fifo_e_conferido(self):
        fifo = self.raiz / "projects" / "proj-a" / "decisoes" / "fifo-ficticio.json"
        fifo.parent.mkdir(exist_ok=True)
        os.mkfifo(fifo)
        codigo, _r, erro, _ = self.pedir("proj-b", "status", prazo=60)
        self.assertEqual(codigo, 0, (erro, (self.base / "porteiro-proj-b.err").read_text(encoding="utf-8")))
        do_a: dict = {}
        t = threading.Thread(target=lambda: do_a.update(r=self.pedir(
            "proj-a", "decisao", "verificar", "--arquivo", str(fifo), prazo=150)), daemon=True)
        t.start()
        time.sleep(3)  # no kit de antes, o do proj-a já está parado no FIFO, com a vez do banco na mão
        codigo_b, _st, erro_b, duracao_b = self.pedir("proj-b", "status", prazo=60)
        for _ in range(240):  # solta o kit de antes, parado na abertura do FIFO, para o teste não esperar o prazo
            if not t.is_alive():
                break
            try:
                os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))
            except OSError:
                pass
            t.join(0.5)
        self.assertEqual(codigo_b, 0, f"o status do proj-b não rodou ({duracao_b:.1f} s): {erro_b}")
        self.assertLess(duracao_b, self.mod.IDADE_MAXIMA_S)
        codigo_a, r_a, erro_a, duracao_a = do_a["r"]
        self.assertEqual((codigo_a, r_a and r_a.get("valida")), (3, False), erro_a)
        self.assertLess(duracao_a, self.mod.IDADE_MAXIMA_S, "o FIFO prendeu o kit do proj-a")


class TestRegistroNaoPrendeAVezDoBanco(PorteirosCase):
    """Revisão 1 do KITDEC (POR-03): o registro.jsonl do proj-a arrendado por outro processo (`decisao registrar`) e o
    registro além do teto de linhas (`tarefa concluir`) não seguram a vez do banco do proj-b."""

    porteiros = ("proj-a", "proj-b")
    ancora_de_ensaio = True

    def decisao_assinada(self) -> Path:
        """Aceite preparado pela fila do proj-a e assinado com a chave de ENSAIO (o titular, no terminal dele)."""
        tarefa = self.tarefa_com_entrega()
        codigo, r, erro, _ = self.pedir("proj-a", "decisao", "preparar", "--projeto", "proj-a", "--tarefa", tarefa,
                                        "--entrega", "outputs/entrega.md", "--tipo", "aceite", "--motivo",
                                        "Aceito a entrega fictícia.", "--shell", "bash", prazo=60)
        self.assertEqual(codigo, 0, erro)
        arq = Path(r["decisao"])
        subprocess.run([self.keygen, "-Y", "sign", "-f", str(self.chave), "-n", "fundacao-decisao", str(arq)],
                       check=True, capture_output=True)
        return arq

    def status_do_proj_b_durante(self, *pedido_do_a, soltar=None) -> tuple:
        """O pedido do proj-a numa thread e, 3 s depois, o `status` do proj-b; então solta o que prende o kit de antes
        (`soltar`) e devolve (código, erro, duração) do proj-b e a resposta do proj-a."""
        do_a: dict = {}
        t = threading.Thread(target=lambda: do_a.update(r=self.pedir("proj-a", *pedido_do_a, prazo=150)),
                             daemon=True)
        t.start()
        time.sleep(3)
        codigo_b, _st, erro_b, duracao_b = self.pedir("proj-b", "status", prazo=60)
        if soltar is not None:
            soltar()
        t.join(150)
        self.assertFalse(t.is_alive(), "o pedido do proj-a não voltou")
        return (codigo_b, erro_b, duracao_b), do_a["r"]

    def test_registro_arrendado_nao_prende_a_vez(self):
        arq = self.decisao_assinada()
        reg = arq.parent / "registro.jsonl"
        reg.write_bytes(b"")  # existe: o registrar chega ao acréscimo, que conflita com o arrendamento de leitura
        arrendador = subprocess.Popen([sys.executable, "-I", "-c", ARRENDADOR, str(reg)], stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, text=True)

        def soltar():
            if arrendador.poll() is None:
                arrendador.kill()
            arrendador.wait(10)
        self.addCleanup(lambda: (soltar(), arrendador.stdin.close(), arrendador.stdout.close()))
        linha = arrendador.stdout.readline().strip()
        if linha != "pronto":  # o sistema de arquivos recusa (no DrvFs, EINVAL): não há o que medir
            self.skipTest(f"arrendamento indisponível aqui ({linha or arrendador.wait(10)})")
        (codigo_b, erro_b, duracao_b), (codigo_a, _r, erro_a, duracao_a) = self.status_do_proj_b_durante(
            "decisao", "registrar", "--arquivo", str(arq), soltar=soltar)
        self.assertEqual(codigo_b, 0, f"o status do proj-b não rodou ({duracao_b:.1f} s): {erro_b}")
        self.assertLess(duracao_b, self.mod.IDADE_MAXIMA_S)
        self.assertEqual(codigo_a, 2, f"o proj-a voltou {codigo_a} em {duracao_a:.1f} s: {erro_a}")
        self.assertIn("E_PATH_ESCAPE", erro_a)
        self.assertLess(duracao_a, self.mod.IDADE_MAXIMA_S, "o arrendamento prendeu o kit do proj-a")
        self.assertEqual(reg.read_bytes(), b"")

    def test_registro_alem_do_teto_de_linhas_nao_prende_a_vez(self):
        arq = self.decisao_assinada()
        codigo, r, erro, _ = self.pedir("proj-a", "decisao", "registrar", "--arquivo", str(arq), prazo=60)
        self.assertEqual((codigo, r and r.get("registro")), (0, "registrada agora"), erro)
        with open(arq.parent / "registro.jsonl", "ab") as f:  # objetos válidos, de nenhuma tarefa
            f.write(b"{}\n" * LINHAS_ALEM_DO_TETO)
        (codigo_b, erro_b, duracao_b), (codigo_a, _r, erro_a, duracao_a) = self.status_do_proj_b_durante(
            "tarefa", "concluir", "--decisao", str(arq))
        self.assertEqual(codigo_b, 0, f"o status do proj-b não rodou ({duracao_b:.1f} s): {erro_b}")
        self.assertLess(duracao_b, self.mod.IDADE_MAXIMA_S)
        self.assertEqual(codigo_a, 2, f"o proj-a voltou {codigo_a} em {duracao_a:.1f} s: {erro_a}")
        self.assertIn("E_VALIDATION", erro_a)
        self.assertLess(duracao_a, self.mod.IDADE_MAXIMA_S, "a análise do registro prendeu o kit do proj-a")


if __name__ == "__main__":
    unittest.main()
