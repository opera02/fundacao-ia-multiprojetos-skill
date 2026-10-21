"""A suíte de conformidade de uma fundação implantada não acusa, para sempre, uma configuração local aprovada
(1.5.0; implantação real de 2026-10-20: `test_politica_distribuida_mantem_sigiloso_so_local` falhava em toda
execução depois da DECISAO-003, que mudou `task_routes.sigiloso` da raiz). A política distribuída continua
conferida no kit da skill; na raiz implantada, o `instalar_kit.py` lista a configuração preservada. Desde a 1.7.0
(proposta 5), a rota sigilosa alterada só vale com o hash da política ligado à decisão em
registry/configuracao-decidida.json; antes, a conferência era pulada e um desvio sem decisão passava em silêncio. Desde
a 1.7.4 (avaliação E11, F-05), a decisão é um aceite assinado sobre a política exata, e o desvio sem ele fica sem
efeito ao carregar a política (vale a rota distribuída): a suíte da raiz confere a rota que vale de fato, e o `checar`
da atualização avisa."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from apoio import ENV, rodar_script


class TestConformidadeComConfiguracaoLocal(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="conformidade-local-"))
        self.raiz = self.tmp / "raiz"
        r = rodar_script("instalar_kit.py", "--destino", self.raiz)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def alterar_rota_sigilosa(self) -> Path:
        politica = self.raiz / "registry" / "route_policy.json"
        p = json.loads(politica.read_text(encoding="utf-8"))
        p["task_routes"]["sigiloso"] = ["cli_assinatura", "local"]  # como a DECISAO-003 da fundação real
        politica.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
        return politica

    def suite_de_rotas(self) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p",
                               "test_eventos_rotas.py"], cwd=str(self.raiz), env=ENV, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=600)

    def test_rota_sigilosa_alterada_por_decisao_nao_reprova_a_suite_da_raiz(self):
        politica = self.alterar_rota_sigilosa()
        decisao = self.raiz / "docs" / "decisoes" / "DECISAO-003.md"
        decisao.parent.mkdir(parents=True)
        decisao.write_text("# DECISAO-003 (fictícia)\n", encoding="utf-8")
        (self.raiz / "registry" / "configuracao-decidida.json").write_text(json.dumps({
            "schema_version": "fundacao.configuracao_decidida/1",
            "itens": [{"arquivo": "registry/route_policy.json", "sha256": hashlib.sha256(politica.read_bytes()).hexdigest(),
                       "decisao": "docs/decisoes/DECISAO-003.md"}]}), encoding="utf-8")
        r = self.suite_de_rotas()
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])

    def test_rota_sigilosa_alterada_sem_aceite_assinado_fica_sem_efeito_e_o_checar_avisa(self):
        self.alterar_rota_sigilosa()
        r = self.suite_de_rotas()
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        efetiva = subprocess.run([sys.executable, "-B", "-c", "import json; from fundacao.core.routing import load_policy; "
                                  "print(json.dumps(load_policy('.')['task_routes']['sigiloso']))"], cwd=str(self.raiz),
                                 env=ENV, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        self.assertEqual(json.loads(efetiva.stdout), ["local"], efetiva.stderr[-800:])
        init = subprocess.run([sys.executable, "-B", "-m", "fundacao", "init", "--admin", "titular-ensaio"],
                              cwd=str(self.raiz), env=ENV, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=120)
        self.assertEqual(init.returncode, 0, init.stderr[-800:])
        res = json.loads(rodar_script("atualizar_fundacao.py", "checar", "--raiz", self.raiz).stdout)
        self.assertTrue(res["rota_sigilosa"]["conferida"], res["rota_sigilosa"])
        self.assertTrue(any(a.startswith("rota sigilosa:") for a in res["avisos"]), res["avisos"])

    def test_politica_de_backup_local_nao_reprova_a_suite_da_raiz(self):
        """1.5.1: o ensaio da atualização da fundação real recusou o kit 1.5.0 porque test_backup_completo lia o
        registry/backup_policy.json da raiz implantada em vez de conferir a política padrão."""
        (self.raiz / "registry" / "backup_policy.json").write_text(json.dumps(
            {"schema_version": "fundacao.backup_policy/1", "incluir": ["docs", "plugins", ".claude/hooks"]}),
            encoding="utf-8")
        r = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p",
                            "test_backup_completo.py"], cwd=str(self.raiz), env=ENV, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=600)
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])


if __name__ == "__main__":
    unittest.main()
