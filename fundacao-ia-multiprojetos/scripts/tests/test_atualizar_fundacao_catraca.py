"""Catraca de testes na atualização da fundação (propostas 5 e 11 da análise do vibe-coding-toolkit, 21/10/2026).

Antes, o ensaio só chamava de regressão uma falha nova: um teste que sumia ou passava a ser pulado no kit novo
saía como "nenhuma regressão". Agora o executor da suíte devolve os IDs rodados e os pulados, e o ensaio para
quando um teste que passava some ou passa a ser pulado — salvo se o kit novo declarar a retirada em
`tests/testes_retirados.json` (ID → versão e motivo). O instalador guarda o arquivo retirado (órfão) no
backup, e o `desfazer` o devolve. Pastas descartáveis; identidade de ensaio; nada no perfil.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from apoio import ENV, SKILL, rodar_script, versao_do_kit

IDENTIDADE = "FUNDACAO_" + "PRINCIPAL"
ID_ANTIGO = "test_antigo_retirado.TestAntigo.test_passa"
TESTE_ANTIGO = "import unittest\n\n\nclass TestAntigo(unittest.TestCase):\n    def test_passa(self):\n        pass\n"
TESTE_QUE_PASSA_A_SER_PULADO = '''import unittest
from pathlib import Path


class TestLocal(unittest.TestCase):
    def test_so_no_kit_antigo(self):
        init = Path(__file__).resolve().parents[1] / "fundacao" / "__init__.py"
        if 'KIT_VERSION = "1.0.0"' not in init.read_text(encoding="utf-8"):
            self.skipTest("kit novo: este teste deixou de valer")
'''


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class TestCatracaDaAtualizacao(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="atualizar-catraca-"))
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

    def teste_antigo_do_kit(self) -> Path:
        """Um kit anterior instalou `tests/test_antigo_retirado.py`, que o kit desta skill não tem mais."""
        arq = self.raiz / "tests" / "test_antigo_retirado.py"
        arq.write_text(TESTE_ANTIGO, encoding="utf-8")
        reg = self.raiz / "registry" / "kit_install.json"
        historico = json.loads(reg.read_text(encoding="utf-8"))
        historico[-1]["copiados"].append({"path": "tests/test_antigo_retirado.py", "sha256": sha(arq)})
        reg.write_text(json.dumps(historico, ensure_ascii=False, indent=2), encoding="utf-8")
        return arq

    def atualizar(self, *args, script: Path | None = None) -> tuple:
        script = script or SKILL / "scripts" / "atualizar_fundacao.py"
        r = subprocess.run([sys.executable, "-B", str(script), *map(str, args)], env=self.env, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=900)
        try:
            return r.returncode, json.loads(r.stdout)
        except ValueError:
            self.fail("saída não é JSON: " + r.stdout[-500:] + r.stderr[-500:])

    def test_teste_retirado_sem_declaracao_para_o_ensaio(self):
        arq = self.teste_antigo_do_kit()
        code, chk = self.atualizar("checar", "--raiz", self.raiz)
        self.assertEqual(chk["mudancas"]["retirar"], ["tests/test_antigo_retirado.py"], chk)
        self.assertFalse(chk["nada_a_fazer"])
        code, res = self.atualizar("aplicar", "--raiz", self.raiz, "--backups", self.backups,
                                   "--padrao-testes", "test_antigo_*.py")
        self.assertEqual((code, res.get("etapa")), (1, "ensaio"), res)
        self.assertEqual(res["testes_sumidos"], [ID_ANTIGO])
        self.assertTrue(arq.is_file())                                         # raiz intacta

    def test_teste_retirado_declarado_passa_e_desfazer_devolve(self):
        arq = self.teste_antigo_do_kit()
        skill = self.tmp / "skill"
        shutil.copytree(SKILL, skill, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "evals"))
        declaracao = {ID_ANTIGO: {"versao": "ensaio", "motivo": "teste retirado de propósito no kit novo"}}
        (skill / "assets" / "fundacao-kit" / "tests" / "testes_retirados.json").write_text(
            json.dumps(declaracao, ensure_ascii=False), encoding="utf-8")
        script = skill / "scripts" / "atualizar_fundacao.py"
        code, res = self.atualizar("aplicar", "--raiz", self.raiz, "--backups", self.backups,
                                   "--padrao-testes", "test_antigo_*.py", script=script)
        self.assertEqual(code, 0, res)
        reg = json.loads(Path(res["registro"]).read_text(encoding="utf-8"))
        self.assertEqual(reg["ensaio"]["testes_sumidos"], [])
        self.assertEqual(reg["ensaio"]["retiradas_declaradas"], [ID_ANTIGO])
        self.assertFalse(arq.exists())
        code, des = self.atualizar("desfazer", "--registro", res["registro"], script=script)
        self.assertEqual(code, 0, des)
        self.assertEqual(des["orfaos_devolvidos"], ["tests/test_antigo_retirado.py"])
        self.assertEqual(arq.read_text(encoding="utf-8"), TESTE_ANTIGO)
        # 1.7.7: o órfão recolocado volta ao registro da instalação; sem isso, o `checar` seguinte o acusaria como
        # executável desconhecido (inventário exato, auditoria Codex Security da 1.7.6, #8).
        code, chk = self.atualizar("checar", "--raiz", self.raiz, script=script)
        self.assertEqual(code, 0, chk)
        self.assertEqual((chk["mudancas"]["retirar"], chk["mudancas"]["executaveis_a_mais"]),
                         (["tests/test_antigo_retirado.py"], []))

    def test_teste_que_passa_a_ser_pulado_e_regressao(self):
        init = self.raiz / "fundacao" / "__init__.py"
        atual = 'KIT_VERSION = "' + versao_do_kit(self.raiz) + '"'
        init.write_text(init.read_text(encoding="utf-8").replace(atual, 'KIT_VERSION = "1.0.0"'), encoding="utf-8")
        reg = self.raiz / "registry" / "kit_install.json"
        historico = json.loads(reg.read_text(encoding="utf-8"))
        for item in historico[-1]["copiados"]:
            if item["path"] == "fundacao/__init__.py":
                item["sha256"] = sha(init)
        reg.write_text(json.dumps(historico, ensure_ascii=False, indent=2), encoding="utf-8")
        # Desde a 1.7.7, teste que o kit não instalou faz o `checar` recusar (auditoria Codex Security da 1.7.6, #8):
        # o teste que passa a ser pulado vem no kit novo, numa cópia da skill, como um teste do próprio kit.
        skill = self.tmp / "skill"
        shutil.copytree(SKILL, skill, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "evals"))
        for base in (skill / "assets" / "fundacao-kit", self.raiz):
            (base / "tests" / "test_local_pula.py").write_text(TESTE_QUE_PASSA_A_SER_PULADO, encoding="utf-8")
        code, res = self.atualizar("aplicar", "--raiz", self.raiz, "--backups", self.backups,
                                   "--padrao-testes", "test_local_*.py",
                                   script=skill / "scripts" / "atualizar_fundacao.py")
        self.assertEqual((code, res.get("etapa")), (1, "ensaio"), res)
        self.assertEqual(res["pulados_novos"], ["test_local_pula.TestLocal.test_so_no_kit_antigo"])
        self.assertEqual(versao_do_kit(self.raiz), "1.0.0")                   # raiz intacta


if __name__ == "__main__":
    unittest.main()
