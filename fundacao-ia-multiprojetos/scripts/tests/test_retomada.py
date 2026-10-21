"""`scripts/retomada.py` — validação estrutural, não autorização (auditoria da 1.4.1, A17; revisão de
segurança da 1.4.5, #10).

Até a 1.4.5 a saída do `validar` trazia só `ok`/`campos_ausentes`, e o modelo chamava o arquivo de
"estado confiável" com "permissões que continuam válidas". Agora a saída declara que a validação é
estrutural e avisa, sem bloquear, quando falta a origem das autorizações; os campos obrigatórios não
mudaram, e um registro no formato antigo continua válido (controle). Os demais falham na 1.4.5.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from apoio import SKILL, rodar_script

MODELO = SKILL / "assets" / "templates" / "RETOMADA.md"
OBRIGATORIOS = {
    "project_id:": "juridico-lab",
    "run_id de referência:": "lab-001",
    "Objetivo atual:": "criar a fundação de laboratório (dados fictícios)",
    "Estado confirmado:": "kit instalado; init feito",
    "Versão do código/configuração:": "kit 1.4.1",
    "Evidências:": "evidence/ambiente/inventario-2026-10-20.json",
    "Bloqueios de acesso, custo ou decisão:": "nenhum",
    "Próxima ação autorizada:": "criar o projeto reversa-lab",
    "Ações já realizadas que não devem ser repetidas:": "nenhum",
    "Última conferência do registro:": "2026-10-20 10:00 -0300",
}


def preencher(valores: dict[str, str], texto: str | None = None) -> str:
    linhas = []
    for linha in (texto or MODELO.read_text(encoding="utf-8")).splitlines():
        for chave, valor in valores.items():
            if linha.startswith(chave):
                linha = f"{chave} {valor}"
        if linha.strip() == "1. (preencher)":
            linha = "1. evidence/ambiente/inventario-2026-10-20.json"
        linhas.append(linha)
    return "\n".join(linhas) + "\n"


class TestRetomadaEstrutural(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="retomada-teste-"))

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def validar(self, texto: str):
        arq = self.base / "RETOMADA.md"
        arq.write_text(texto, encoding="utf-8")
        p = rodar_script("retomada.py", "validar", "--arquivo", arq)
        return p, json.loads(p.stdout)

    def test_modelo_nao_se_apresenta_como_autorizacao(self):
        texto = MODELO.read_text(encoding="utf-8")
        self.assertIn("Origem das autorizações:", texto)
        self.assertNotIn("continuam válidos", texto)
        self.assertNotIn("estado confiável", texto)

    def test_saida_declara_validacao_estrutural(self):
        p, dados = self.validar(preencher(OBRIGATORIOS))
        self.assertEqual((p.returncode, dados["ok"], dados["campos_ausentes"]), (0, True, []))
        self.assertIn("estrutural", dados.get("validacao", ""))

    def test_sem_origem_das_autorizacoes_avisa_sem_bloquear(self):
        p, dados = self.validar(preencher(OBRIGATORIOS))
        self.assertEqual(p.returncode, 0)
        self.assertTrue(any("origem" in aviso for aviso in dados.get("avisos", [])), dados)

    def test_origem_preenchida_nao_avisa(self):
        valores = {**OBRIGATORIOS, "Origem das autorizações:":
                   "apr-001: titular; criar projeto reversa-lab; fundação de laboratório; até 2026-10-31"}
        p, dados = self.validar(preencher(valores))
        self.assertEqual((p.returncode, dados.get("avisos")), (0, []))

    def test_controle_formato_antigo_continua_valido(self):
        antigo = "\n".join(linha for linha in MODELO.read_text(encoding="utf-8").splitlines()
                           if not linha.startswith(("Origem das autorizações:", "Permissões e limites")))
        antigo += "\nPermissões e limites que continuam válidos: titular é administrador\n"
        p, dados = self.validar(preencher(OBRIGATORIOS, antigo))
        self.assertEqual((p.returncode, dados["ok"]), (0, True))


if __name__ == "__main__":
    unittest.main()
