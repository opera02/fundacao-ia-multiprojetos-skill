"""Atualização da fundação num só comando (atualizar_fundacao.py, 1.5.0): `checar` separa versão antiga de
alteração local sem escrever; `aplicar` faz backup ANTES, ensaia o kit novo numa cópia restaurada, promove,
faz backup DEPOIS e registra; regressão no ensaio não toca a raiz; `desfazer` devolve o código e recusa quando
o esquema do banco mudou. A versão "antiga" é simulada trocando a KIT_VERSION da raiz e o hash registrado dela."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from apoio import ENV, SCRIPTS, SKILL, rodar_script, versao_do_kit

IDENTIDADE = "FUNDACAO_" + "PRINCIPAL"
TESTE_LOCAL = '''import unittest
from pathlib import Path


class TestLocal(unittest.TestCase):
    def test_versao_antiga(self):
        init = Path(__file__).resolve().parents[1] / "fundacao" / "__init__.py"
        self.assertIn('KIT_VERSION = "1.0.0"', init.read_text(encoding="utf-8"))
'''


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class TestAtualizarFundacao(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="atualizar-fundacao-"))
        self.raiz, self.backups = self.tmp / "raiz", self.tmp / "backups"
        r = rodar_script("instalar_kit.py", "--destino", self.raiz)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = subprocess.run([sys.executable, "-B", "-m", "fundacao", "--raiz", str(self.raiz), "init", "--admin",
                            "titular-ensaio"], cwd=str(self.raiz), env=ENV, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.env = {**ENV, IDENTIDADE: "titular-ensaio"}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def versao_antiga(self) -> None:
        """A raiz passa a declarar 1.0.0, com o hash registrado como se fosse a versão instalada."""
        init = self.raiz / "fundacao" / "__init__.py"
        atual = 'KIT_VERSION = "' + versao_do_kit(self.raiz) + '"'
        init.write_text(init.read_text(encoding="utf-8").replace(atual, 'KIT_VERSION = "1.0.0"'), encoding="utf-8")
        reg = self.raiz / "registry" / "kit_install.json"
        historico = json.loads(reg.read_text(encoding="utf-8"))
        for item in historico[-1]["copiados"]:
            if item["path"] == "fundacao/__init__.py":
                item["sha256"] = sha(init)
        reg.write_text(json.dumps(historico, ensure_ascii=False, indent=2), encoding="utf-8")

    def atualizar(self, *args, env=None, script: Path | None = None) -> tuple:
        r = subprocess.run([sys.executable, "-B", str(script or SCRIPTS / "atualizar_fundacao.py"), *map(str, args)],
                           env=env or self.env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=900)
        try:
            return r.returncode, json.loads(r.stdout)
        except ValueError:
            self.fail("saída não é JSON: " + r.stdout[-500:] + r.stderr[-500:])

    def foto(self) -> dict:
        return {p.relative_to(self.raiz).as_posix(): sha(p) for p in self.raiz.rglob("*")
                if p.is_file() and "state" not in p.relative_to(self.raiz).parts}

    def test_checar_separa_versao_antiga_de_alteracao_local_sem_escrever(self):
        self.versao_antiga()
        antes = self.foto()
        code, res = self.atualizar("checar", "--raiz", self.raiz)
        self.assertEqual(code, 0, res)
        self.assertEqual(res["mudancas"]["atualizar"], ["fundacao/__init__.py"])
        self.assertEqual(res["mudancas"]["alterados_localmente"], [])
        self.assertEqual((res["kit_na_raiz"], res["identidade"]), ("1.0.0", "titular-ensaio"))
        ids = self.raiz / "fundacao" / "core" / "ids.py"
        ids.write_text(ids.read_text(encoding="utf-8") + "# alteração local\n", encoding="utf-8")
        code, res = self.atualizar("checar", "--raiz", self.raiz)
        self.assertEqual(code, 1)
        self.assertFalse(res["pode_aplicar"])
        self.assertEqual([a["path"] for a in res["mudancas"]["alterados_localmente"]], ["fundacao/core/ids.py"])
        sem_identidade = {k: v for k, v in self.env.items() if k != IDENTIDADE}
        code, res = self.atualizar("aplicar", "--raiz", self.raiz, "--backups", self.backups, env=sem_identidade)
        self.assertEqual((code, res["etapa"]), (1, "checar"))
        self.assertTrue(any("identidade ausente" in m for m in res["checar"]["motivos"]))
        antes["fundacao/core/ids.py"] = sha(ids)
        self.assertEqual(self.foto(), antes)                                      # nada escrito pelo script
        self.assertFalse(self.backups.exists())

    def test_aplicar_com_ensaio_e_desfazer(self):
        self.versao_antiga()
        code, res = self.atualizar("aplicar", "--raiz", self.raiz, "--backups", self.backups,
                                   "--padrao-testes", "test_local_*.py")
        self.assertEqual(code, 0, res)
        reg = json.loads(Path(res["registro"]).read_text(encoding="utf-8"))
        self.assertEqual((reg["kit_antes"], reg["kit_depois"]), ("1.0.0", versao_do_kit(self.raiz)))
        self.assertEqual(reg["ensaio"]["regressoes"], [])
        for etapa in ("antes", "depois"):
            self.assertTrue((Path(reg[etapa]["pasta"]) / "manifest.json").is_file())
        code, chk = self.atualizar("checar", "--raiz", self.raiz)
        self.assertTrue(chk["nada_a_fazer"], chk)
        code, des = self.atualizar("desfazer", "--registro", res["registro"])
        self.assertEqual(code, 0, des)
        self.assertEqual(versao_do_kit(self.raiz), "1.0.0")
        self.assertEqual(des["devolvidos"], ["fundacao/__init__.py"])
        # 1.7.7: o registro da instalação volta a descrever o código devolvido; antes, o `checar` seguinte acusava o
        # arquivo devolvido como "alterado localmente" e a nova atualização ficava bloqueada.
        code, chk = self.atualizar("checar", "--raiz", self.raiz)
        self.assertEqual(code, 0, chk)
        self.assertEqual((chk["mudancas"]["atualizar"], chk["mudancas"]["alterados_localmente"]),
                         (["fundacao/__init__.py"], []))

    def test_regressao_no_ensaio_nao_toca_a_raiz(self):
        # Desde a 1.7.7, teste que o kit não instalou faz o `checar` recusar antes de qualquer importação (auditoria
        # Codex Security da 1.7.6, #8; test_auditoria_1_7_6_atualizador.py): o teste que regride vem no kit novo,
        # numa cópia da skill, como um teste do próprio kit.
        skill = self.tmp / "skill"
        shutil.copytree(SKILL, skill, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "evals"))
        self.versao_antiga()
        for base in (skill / "assets" / "fundacao-kit", self.raiz):
            (base / "tests" / "test_local_versao.py").write_text(TESTE_LOCAL, encoding="utf-8")
        antes = self.foto()
        code, res = self.atualizar("aplicar", "--raiz", self.raiz, "--backups", self.backups,
                                   "--padrao-testes", "test_local_*.py",
                                   script=skill / "scripts" / "atualizar_fundacao.py")
        self.assertEqual((code, res["etapa"]), (1, "ensaio"), res)
        self.assertEqual(res["regressoes"], ["test_local_versao.TestLocal.test_versao_antiga"])
        self.assertTrue(Path(res["registro"]).name.startswith("falha-atualizacao-kit-"))
        depois = {k: v for k, v in self.foto().items() if not k.startswith("evidence/atualizacoes/")}
        self.assertEqual(depois, antes)                                           # raiz intacta
        self.assertIsNone(res["copia_de_ensaio"])                                 # cópia com dados apagada (1.5.1)
        self.assertIn("1.0.0", res["ensaio"]["suite_na_copia_atualizada"]["detalhes"][res["regressoes"][0]])

    def test_desfazer_recusa_banco_com_esquema_novo(self):
        registro = self.raiz / "evidence" / "atualizacoes" / "atualizacao.json"  # onde o aplicar grava (1.7.0)
        registro.parent.mkdir(parents=True, exist_ok=True)
        registro.write_text(json.dumps({"raiz": str(self.raiz), "user_version_antes": -1,
                                        "antes": {"pasta": "copia-antes"},
                                        "promocao": {"instalar_kit": {"substituidos": [], "copiados": []}}}),
                            encoding="utf-8")
        antes = self.foto()
        code, res = self.atualizar("desfazer", "--registro", registro)
        self.assertEqual((code, res["etapa"]), (1, "desfazer"))
        self.assertIn("mudou de esquema", res["motivo"])
        self.assertEqual(self.foto(), antes)


if __name__ == "__main__":
    unittest.main()
