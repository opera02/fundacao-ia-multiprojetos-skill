"""Porteiro com o kit de verdade (1.7.10; contratos do lote 2, §4): uma fundação fictícia numa pasta temporária, com o
kit da skill copiado (a versão marcada 1.7.10 se o __init__ ainda disser menos: o aperto de mão exige a trava) e dois
projetos. Pelo cliente do kit e pelo porteiro, a sessão do proj-a vê só o proj-a com a identidade sessao-proj-a, cria
e lê tarefas e lições dele, não alcança o proj-b (a lição dele pelo id é negada e fica na trilha) nem a auditoria
(`eventos` e `memoria licao historico` ficam fora do mapa na 1.7.10: emenda E2), e o banco fica travado para o Windows
enquanto o porteiro roda. Só no Linux (WSL ou a CI pública)."""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from apoio import ENV, KIT, versao_do_kit

from test_porteiro import PORTEIRO, carregar
from test_porteiro_fila import LINUX

if str(KIT) not in sys.path:
    sys.path.insert(0, str(KIT))
from fundacao import porteiro_cliente  # noqa: E402
from fundacao.core import trava_banco  # noqa: E402

IDENTIDADE = "FUNDACAO_" + "PRINCIPAL"
FORA_DO_REGISTRY = {"kit_backup", "kit_preparo", "kit_install.json", "atualizacoes.jsonl", "inventario-host.json",
                    "ultima-copia.json"}


@unittest.skipUnless(LINUX, "porteiro: só no Linux")
class TestPorteiroComOKit(unittest.TestCase):
    def setUp(self):
        self.mod = carregar()
        self.base = Path(tempfile.mkdtemp(prefix="porteiro-kit-1710-"))
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
        self.env = {k: v for k, v in ENV.items() if not k.startswith("FUNDACAO_")}
        self.kit("init", "--admin", "titular-ficticio")
        for projeto in ("proj-a", "proj-b"):
            self.kit("projeto", "criar", "--id", projeto, "--nome", f"Projeto {projeto}", "--finalidade",
                     "Ensaio fictício do porteiro")
        cfg = {"schema_version": "fundacao.porteiro/1", "raiz": str(self.raiz), "projeto": "proj-a",
               "kit_sha256": self.mod.sha256_do_kit(self.raiz), "assinante": "titular-ficticio",
               "operacoes": {"fundacao": {}}}
        self.config = self.base / "etc" / "porteiro.json"
        self.config.parent.mkdir()
        self.config.write_text(json.dumps(cfg), encoding="utf-8")
        self.fila = self.raiz / "projects" / "proj-a" / ".porteiro"
        casa = self.base / "casa"
        casa.mkdir()
        with open(self.base / "porteiro.err", "w", encoding="utf-8") as erros:
            self.proc = subprocess.Popen([sys.executable, "-I", "-B", str(PORTEIRO), "servir", "--config",
                                          str(self.config), "--fila", str(self.fila), "--pid-lancador",
                                          str(os.getpid())], env={"HOME": str(casa), "PATH": "/usr/bin:/bin"},
                                         stdout=subprocess.DEVNULL, stderr=erros)
        self.addCleanup(self.parar)
        vida, limite = self.fila / "respostas" / porteiro_cliente.VIDA, time.monotonic() + 60
        while time.monotonic() < limite and self.proc.poll() is None:
            try:
                if json.loads(vida.read_text(encoding="utf-8"))["estado"] != "iniciando":
                    break
            except (OSError, ValueError, KeyError):
                pass
            time.sleep(0.1)

    def kit(self, *args) -> dict:
        r = subprocess.run([sys.executable, "-B", "-m", "fundacao", "--raiz", str(self.raiz), *args],
                           capture_output=True, text=True, encoding="utf-8", cwd=str(self.raiz), timeout=120,
                           env={**self.env, IDENTIDADE: "titular-ficticio"})
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def parar(self) -> None:
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            self.proc.wait(30)

    def pedir(self, *argv) -> tuple[int, dict | None, dict | None]:
        r = porteiro_cliente.pedir(self.fila, list(argv), prazo=120)
        saida = json.loads(r["stdout"]) if r["stdout"].strip() else None
        erro = json.loads(r["stderr"].strip().splitlines()[-1]) if r["stderr"].strip() else None
        return r["codigo"], saida, erro

    def test_sessao_travada_pelo_porteiro_com_o_kit_de_verdade(self):
        codigo, st, erro = self.pedir("status")
        self.assertEqual(codigo, 0, (erro, (self.base / "porteiro.err").read_text(encoding="utf-8")))
        self.assertEqual((st["identidade"], st["projeto_travado"], st["projetos_autorizados"]),
                         ("sessao-proj-a", "proj-a", ["proj-a"]))
        self.assertNotIn("proj-b", json.dumps(st))
        codigo, r, erro = self.pedir("tarefa", "criar", "--projeto", "proj-a", "--objetivo", "tarefa fictícia")
        self.assertEqual(codigo, 0, erro)
        codigo, tarefa, erro = self.pedir("tarefa", "ver", "--projeto", "proj-a", "--id", r["task_id"])
        self.assertEqual((codigo, tarefa["created_by"]), (0, "sessao-proj-a"), erro)
        codigo, _r, erro = self.pedir("tarefa", "criar", "--projeto", "proj-b", "--objetivo", "x")
        self.assertEqual((codigo, erro["error"]["code"]), (2, "E_PORTEIRO"))
        codigo, r, erro = self.pedir("conhecimento", "listar", "--projeto", "proj-a")
        self.assertEqual((codigo, r["projeto"]), (0, "proj-a"), erro)
        codigo, _r, erro = self.pedir("eventos", "verificar")
        self.assertEqual((codigo, erro["error"]["code"]), (2, "E_PORTEIRO"))  # fora do mapa na 1.7.10 (emenda E2)
        codigo, lic, erro = self.pedir("memoria", "licao", "propor", "--projeto", "proj-a", "--op-id", "op-1",
                                       "--gatilho", "quando houver prazo fictício", "--licao", "conferir o prazo",
                                       "--evidencia", "outputs/nota.md", "--confianca", "media")
        self.assertEqual(codigo, 0, erro)
        codigo, _r, erro = self.pedir("memoria", "licao", "historico", "--memoria", lic["memory_id"])
        self.assertEqual((codigo, erro["error"]["code"]), (2, "E_PORTEIRO"))  # fora do mapa na 1.7.10 (emenda E2)
        alheia = self.kit("memoria", "licao", "propor", "--projeto", "proj-b", "--op-id", "op-b", "--gatilho",
                          "quando houver prazo fictício", "--licao", "lição do outro projeto", "--evidencia",
                          "outputs/nota.md", "--confianca", "media")["memory_id"]
        for _vez in range(2):  # a lição do outro projeto pelo id: o kit travado nega e registra a negativa
            codigo, _r, erro = self.pedir("memoria", "licao", "pendente", "--memoria", alheia)
            self.assertEqual((codigo, erro["error"]["code"]), (2, "E_VALIDATION"))
            self.assertIn("não encontrada", erro["error"]["message"])
            self.assertNotIn("proj-b", json.dumps(erro))
        for argv in (("init", "--admin", "x"), ("acl", "registrar", "--principal", "intrusa"),
                     ("projeto", "listar"), ("backup", "situacao")):
            with self.subTest(argv=argv):
                self.assertEqual(self.pedir(*argv)[0], 2)
        estado = self.raiz / "state"
        with self.assertRaises(trava_banco.BancoTravado):  # o kit do Windows não abre o banco agora
            trava_banco.conferir(estado, lado="windows")
        self.parar()
        self.assertEqual(self.proc.returncode, 0)
        trava_banco.conferir(estado, lado="windows")  # o porteiro saiu e soltou a trava
        self.assertEqual(self.kit("status")["projetos_autorizados"], ["proj-a", "proj-b"])
        con = sqlite3.connect(f"file:{estado / 'state.sqlite'}?mode=ro", uri=True)
        try:
            principais = {r[0] for r in con.execute("SELECT principal_id FROM principal")}
            negativas = con.execute("SELECT COUNT(*) FROM event WHERE kind = 'access_denied' AND subject = ?",
                                    ("sessao-proj-a",)).fetchone()[0]
        finally:
            con.close()
        self.assertEqual(principais, {"titular-ficticio"}, "nem a sessão nem uma intrusa viraram linha no banco")
        self.assertGreaterEqual(negativas, 2, "as negativas da sessão ficam na trilha")


if __name__ == "__main__":
    unittest.main()
