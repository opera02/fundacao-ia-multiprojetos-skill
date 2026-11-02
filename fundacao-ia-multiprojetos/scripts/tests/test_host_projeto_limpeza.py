"""Pastas de trabalho de um porteiro morto por SIGKILL (1.7.10; orientação do coordenador na reconferência do lote 2).

O porteiro.py (pacote PORTEIRO) cria `~/.fundacao/porteiro/<p>/trabalho-*` com tempfile.mkdtemp e só a apaga ao
encerrar; morto por SIGKILL, ela fica, com a cópia privada do kit. O lançador chama `preparo_host.py limpar-porteiro`
antes de iniciar o porteiro e ao sair, e o ajudante só apaga sem porteiro deste projeto de pé e sem ninguém usando a
pasta (lido em /proc), sem seguir ligação. Aqui: o que sai e o que fica (o resto da pasta, ligações e o destino delas,
nomes fora da forma do mkdtemp), o porteiro de pé (deste projeto e de outro), o kit órfão (pasta atual ou argumento
dentro da pasta), /proc ilegível e a pasta do porteiro por ligação. Processos de ensaio são `python -c` com a linha de
comando do porteiro; pastas descartáveis, nada da casa real. Só no Linux (no Windows, nada é apagado).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from apoio import ENV
from test_host_projeto_apoio import LINUX, carregar_preparo

DORMIR = "import time; time.sleep(60)"


class _Base(unittest.TestCase):
    def setUp(self):
        self.m = carregar_preparo()
        self.base = Path(tempfile.mkdtemp(prefix="limpeza-porteiro-1710-")).resolve()
        self.casa = self.base / "home"
        self.raiz = self.base / "Fundacao Ensaio"
        self.fila = f"{self.raiz.as_posix()}/projects/caso-real/.porteiro"
        self.pasta = self.casa / ".fundacao" / "porteiro" / "caso-real"
        self.trabalho = self.pasta / "trabalho-abcd1234"
        (self.trabalho / "kit-x1y2z3w4" / "fundacao" / "core").mkdir(parents=True)
        (self.trabalho / "kit-x1y2z3w4" / "fundacao" / "__init__.py").write_text("KIT_VERSION = 'ensaio'\n",
                                                                                 encoding="utf-8")
        (self.trabalho / "kit-x1y2z3w4" / "fundacao" / "core" / "db.py").write_text("x = 1\n", encoding="utf-8")
        (self.pasta / "registro.jsonl").write_text("{}\n", encoding="utf-8")  # o registro do porteiro fica
        (self.pasta / "saida.log").write_text("saída de ensaio\n", encoding="utf-8")
        self.processos = []

    def tearDown(self):
        for p in self.processos:
            p.kill()
            p.wait(timeout=30)
        shutil.rmtree(self.base, ignore_errors=True)

    def limpar(self, **kw) -> dict:
        return self.m.limpar_trabalho_do_porteiro(self.casa, self.raiz, "caso-real", **kw)

    def processo(self, *args, cwd: Path | None = None) -> subprocess.Popen:
        p = subprocess.Popen([sys.executable, "-c", DORMIR, *map(str, args)], cwd=str(cwd) if cwd else None,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.processos.append(p)
        return p

    def encerrar(self, p: subprocess.Popen) -> None:
        p.kill()
        p.wait(timeout=30)
        self.processos.remove(p)


@unittest.skipUnless(LINUX, "o porteiro e o /proc são do Ubuntu (WSL2)")
class LimpezaNoLinux(_Base):
    def test_apaga_so_as_pastas_de_trabalho_sem_seguir_ligacao(self):
        fora = self.base / "fora"
        fora.mkdir()
        (fora / "importante.txt").write_text("não pode sumir\n", encoding="utf-8")
        (self.trabalho / "kit-x1y2z3w4" / "ligada").symlink_to(fora, target_is_directory=True)
        (self.trabalho / "arquivo-ligado").symlink_to(fora / "importante.txt")
        (self.pasta / "trabalho-naoconfere").mkdir()  # fora da forma do mkdtemp: não é do porteiro
        res = self.limpar()
        self.assertEqual(res["apagadas"], ["trabalho-abcd1234"], res)
        self.assertEqual(res["mantidas"], [])
        self.assertFalse(os.path.lexists(self.trabalho))
        self.assertEqual((fora / "importante.txt").read_text(encoding="utf-8"), "não pode sumir\n")
        self.assertEqual(sorted(os.listdir(self.pasta)), ["registro.jsonl", "saida.log", "trabalho-naoconfere"])
        self.assertEqual(self.limpar()["apagadas"], [])  # segunda vez: nada a fazer

    def test_ligacao_no_lugar_da_pasta_de_trabalho_fica_e_nao_e_seguida(self):
        alvo = self.base / "alvo-da-ligacao"
        alvo.mkdir()
        (alvo / "dado.txt").write_text("fica\n", encoding="utf-8")
        (self.pasta / "trabalho-ligado12").symlink_to(alvo, target_is_directory=True)
        res = self.limpar()
        self.assertEqual(res["apagadas"], ["trabalho-abcd1234"])
        self.assertEqual(res["mantidas"], ["trabalho-ligado12"])
        self.assertIn("ligação", res["motivo"])
        self.assertTrue((self.pasta / "trabalho-ligado12").is_symlink())
        self.assertEqual((alvo / "dado.txt").read_text(encoding="utf-8"), "fica\n")

    def test_pasta_do_porteiro_por_ligacao_nada_sai(self):
        outra = self.base / "outra-casa" / "caso-real"
        outra.parent.mkdir()
        shutil.move(str(self.pasta), str(outra))
        self.pasta.symlink_to(outra, target_is_directory=True)
        res = self.limpar()
        self.assertEqual(res["apagadas"], [])
        self.assertIn("sem seguir ligação", res["motivo"])
        self.assertTrue((outra / "trabalho-abcd1234" / "kit-x1y2z3w4" / "fundacao" / "__init__.py").is_file())

    def test_porteiro_do_projeto_de_pe_nada_sai(self):
        porteiro = f"{self.base}/skill/assets/host/wsl/porteiro.py"
        for forma in (["--fila", self.fila], [f"--fila={self.fila}/"]):
            with self.subTest(forma=forma[0]):
                p = self.processo(porteiro, "servir", "--config", "/etc/fundacao-ia/projetos/caso-real/porteiro.json",
                                  *forma, "--pid-lancador", "2")
                res = self.limpar()
                self.assertEqual(res["apagadas"], [], res)
                self.assertEqual(res["mantidas"], ["trabalho-abcd1234"])
                self.assertIn(f"pid {p.pid}", res["motivo"])
                self.assertTrue(self.trabalho.is_dir())
                self.encerrar(p)
        outro = self.processo(porteiro, "servir", "--fila", f"{self.raiz.as_posix()}/projects/lab-a/.porteiro")
        self.assertEqual(self.limpar()["apagadas"], ["trabalho-abcd1234"])  # o porteiro de outro projeto não conta
        self.encerrar(outro)

    def test_porteiro_do_projeto_com_fila_de_outra_raiz_nada_sai(self):
        """Folha da integração, I6 (baixo da reconferência do HOST): a pasta ~/.fundacao/porteiro/<p>/ é do nome do
        projeto, não da raiz. Um porteiro.py deste usuário com a --fila de outra raiz que termina em
        /projects/<p>/.porteiro é porteiro deste projeto: a pasta de trabalho dele fica."""
        porteiro = f"{self.base}/outra-skill/assets/host/wsl/porteiro.py"
        p = self.processo(porteiro, "servir", "--config", "/etc/fundacao-ia/projetos/caso-real/porteiro.json",
                          "--fila", "/outra/raiz/projects/caso-real/.porteiro", "--pid-lancador", "2")
        res = self.limpar()
        self.assertEqual(res["apagadas"], [], res)
        self.assertEqual(res["mantidas"], ["trabalho-abcd1234"])
        self.assertIn(f"pid {p.pid}", res["motivo"])
        self.assertIn("outra raiz", res["motivo"])
        self.assertTrue(self.trabalho.is_dir())
        self.encerrar(p)
        outro = self.processo(porteiro, "servir", "--fila", "/outra/raiz/projects/lab-a/.porteiro")
        self.assertEqual(self.limpar()["apagadas"], ["trabalho-abcd1234"])  # outro projeto, de outra raiz: não conta
        self.encerrar(outro)

    def segurar_trava(self) -> subprocess.Popen:
        """Um processo que toma o flock exclusivo do porteiro.trava (como o _tomar_unico do porteiro.py) sem citar a
        pasta na linha de comando nem rodar dentro dela: só a trava prova que ele está de pé."""
        trava = self.pasta / "porteiro.trava"
        pronto = self.base / "trava-tomada"
        codigo = ("import fcntl, os, time; fd = os.open(os.environ['TRAVA_DE_ENSAIO'], os.O_RDWR | os.O_CREAT, 0o600); "
                  "fcntl.flock(fd, fcntl.LOCK_EX); open(os.environ['PRONTO_DE_ENSAIO'], 'w').close(); time.sleep(60)")
        p = subprocess.Popen([sys.executable, "-c", codigo], cwd=str(self.base), stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             env={**ENV, "TRAVA_DE_ENSAIO": str(trava), "PRONTO_DE_ENSAIO": str(pronto)})
        self.processos.append(p)
        import time
        limite = time.monotonic() + 30
        while not pronto.exists() and time.monotonic() < limite and p.poll() is None:
            time.sleep(0.05)
        self.assertTrue(pronto.exists(), "o processo de ensaio não tomou a trava")
        return p

    def test_trava_do_porteiro_tomada_nada_sai(self):
        """Folha da integração, I6: a prova pelo porteiro.trava (aberta pelo descritor da pasta, O_RDONLY|O_NOFOLLOW, e
        flock LOCK_EX|LOCK_NB): bloqueada = um porteiro deste projeto de pé, mesmo que o /proc não o mostre."""
        p = self.segurar_trava()
        res = self.limpar()
        self.assertEqual((res["apagadas"], res["mantidas"]), ([], ["trabalho-abcd1234"]), res)
        self.assertIn("porteiro.trava", res["motivo"])
        self.assertTrue(self.trabalho.is_dir())
        self.encerrar(p)
        res = self.limpar()
        self.assertEqual(res["apagadas"], ["trabalho-abcd1234"], res)
        self.assertTrue((self.pasta / "porteiro.trava").is_file())  # a trava do porteiro nunca sai

    def test_trava_livre_fica_tomada_durante_a_limpeza_e_ausente_nao_e_criada(self):
        """Tomada pela limpeza, a trava fica com ela até o fim: um porteiro que suba no meio sai sem tocar a fila e
        nenhuma pasta dele é apagada. Sem o porteiro.trava (nenhum porteiro subiu nesta casa), nada é criado."""
        import fcntl
        from unittest import mock
        self.assertEqual(self.limpar()["apagadas"], ["trabalho-abcd1234"])
        self.assertFalse(os.path.lexists(self.pasta / "porteiro.trava"))
        (self.pasta / "trabalho-efgh5678").mkdir()
        (self.pasta / "porteiro.trava").write_bytes(b"")
        vistos, original = [], self.m._apagar_por_descritor

        def espiao(fd_pai, nome, profundidade=0):
            fd = os.open(self.pasta / "porteiro.trava", os.O_RDONLY)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                vistos.append("livre")
            except BlockingIOError:
                vistos.append("tomada")
            finally:
                os.close(fd)
            return original(fd_pai, nome, profundidade)

        with mock.patch.object(self.m, "_apagar_por_descritor", espiao):
            res = self.limpar()
        self.assertEqual(res["apagadas"], ["trabalho-efgh5678"], res)
        self.assertEqual(vistos, ["tomada"])

    def test_trava_que_nao_e_arquivo_comum_nada_sai(self):
        alvo = self.base / "alvo-da-trava"
        alvo.write_bytes(b"")
        trava = self.pasta / "porteiro.trava"
        for nome, criar in (("ligação", lambda: trava.symlink_to(alvo)), ("pasta", lambda: trava.mkdir()),
                            ("fifo", lambda: os.mkfifo(trava))):
            with self.subTest(nome):
                criar()
                res = self.limpar()  # a FIFO não trava a leitura (O_NONBLOCK)
                self.assertEqual((res["apagadas"], res["mantidas"]), ([], ["trabalho-abcd1234"]), res)
                self.assertIn("nada apagado", res["motivo"])
                trava.rmdir() if trava.is_dir() and not trava.is_symlink() else trava.unlink()
        self.assertEqual(self.limpar()["apagadas"], ["trabalho-abcd1234"])

    def test_kit_orfao_de_porteiro_morto_nada_sai(self):
        """O kit roda com a pasta atual na pasta de trabalho e com a cópia e o pycache_prefix nos argumentos: o
        porteiro morreu, mas o pedido ainda roda."""
        for nome, kw in (("pasta atual", {"cwd": self.trabalho}),
                         ("argumento", {"args": [f"pycache_prefix={self.trabalho}"]})):
            with self.subTest(nome):
                p = self.processo(*kw.get("args", ()), cwd=kw.get("cwd"))
                res = self.limpar()
                self.assertEqual(res["apagadas"], [], res)
                self.assertIn(str(p.pid), res["motivo"])
                self.encerrar(p)
        self.assertEqual(self.limpar()["apagadas"], ["trabalho-abcd1234"])

    def test_sem_proc_legivel_nada_sai(self):
        res = self.limpar(proc=str(self.base / "sem-proc"))
        self.assertEqual((res["apagadas"], res["mantidas"]), ([], ["trabalho-abcd1234"]))
        self.assertIn("/proc", res["motivo"])
        self.assertTrue(self.trabalho.is_dir())

    def test_sem_a_pasta_do_porteiro_nada_a_fazer(self):
        shutil.rmtree(self.casa / ".fundacao")
        self.assertEqual(self.limpar(), {"pasta": self.pasta.as_posix(), "apagadas": [], "mantidas": [],
                                         "motivo": None})

    def test_linha_de_comando(self):
        args = [sys.executable, "-I", "-B", str(self.m.__file__), "limpar-porteiro", "--raiz", str(self.raiz),
                "--projeto", "caso-real", "--casa", str(self.casa)]
        r = subprocess.run([*args, "--texto"], capture_output=True, text=True, encoding="utf-8", env=ENV, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("trabalho-abcd1234", r.stdout)
        self.assertFalse(self.trabalho.exists())
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", env=ENV, timeout=120)
        self.assertEqual(json.loads(r.stdout)["apagadas"], [])
        for ruim in (["--casa", "relativa"], ["--projeto", "caso_real"]):
            with self.subTest(ruim=ruim):
                trocado = list(args)
                trocado[trocado.index(ruim[0]) + 1] = ruim[1]
                r = subprocess.run(trocado, capture_output=True, text=True, encoding="utf-8", env=ENV, timeout=120)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


class LimpezaForaDoLinux(_Base):
    @unittest.skipIf(LINUX, "no Linux, a limpeza roda (LimpezaNoLinux)")
    def test_fora_do_linux_nada_e_apagado(self):
        res = self.limpar()
        self.assertEqual(res["apagadas"], [])
        self.assertIn("Linux", res["motivo"])
        self.assertTrue(self.trabalho.is_dir())

    def test_entrada_invalida(self):
        for casa, projeto in (("relativa", "caso-real"), ("", "caso-real"), (str(self.casa), "caso_real")):
            with self.subTest(casa=casa, projeto=projeto), self.assertRaises(self.m.EntradaInvalida):
                self.m.limpar_trabalho_do_porteiro(casa, self.raiz, projeto)

    def test_o_nome_e_o_do_mkdtemp_do_porteiro(self):
        """A forma que a limpeza aceita é a do tempfile.mkdtemp(prefix="trabalho-") que o porteiro usa."""
        nomes = []
        for _ in range(20):
            pasta = Path(tempfile.mkdtemp(prefix="trabalho-", dir=self.base))
            nomes.append(pasta.name)
        self.assertTrue(all(self.m.TRABALHO_DO_PORTEIRO.fullmatch(n) for n in nomes), nomes)
        for nome in ("trabalho-", "trabalho-abc", "trabalho-ABCD1234", "trabalho-abcd1234x", "kit-abcd1234",
                     "trabalho-abcd/123"):
            self.assertIsNone(self.m.TRABALHO_DO_PORTEIRO.fullmatch(nome), nome)


if __name__ == "__main__":
    unittest.main()
