"""Nenhum arquivo do pacote casa os padrões da varredura de segredos da transferência (liberação da 1.7.0).

A montagem da transferência recusa o pacote quando algum arquivo parece trazer chave, token, senha atribuída ou
e-mail. Os falsos positivos já pararam duas liberações: na 1.6.0, o campo com o estado da senha da chave no relatório
do preparo do host; na 1.7.0, o valor fictício `TOKEN = "..."` de um teste do inventário do host. O teste de
regressão da 1.6.1 cobria só os arquivos do preparo do host; este cobre tudo o que entra no pacote (a skill sem
evals/), com os mesmos padrões, para o falso positivo aparecer aqui, e não no meio da liberação.
"""

from __future__ import annotations

import re
import unittest

from apoio import SKILL

PADROES = {  # os mesmos da varredura da transferência (ferramentas de liberação da fundação)
    "chave_de_api": re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}"),
    "token_github": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    "chave_aws": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "token_slack": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "chave_privada": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "senha_ou_token_atribuido": re.compile(
        r"(?i)\b(?:password|senha|passwd|secret|api[_-]?key|token)\s*[:=]\s*['\"][^'\"\s]{8,}['\"]"),
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
}


class TestPacoteSemSegredoAparente(unittest.TestCase):
    def test_nenhum_arquivo_do_pacote_casa_a_varredura(self):
        achados = []
        for arq in sorted(SKILL.rglob("*")):
            rel = arq.relative_to(SKILL).as_posix()
            if not arq.is_file() or rel.startswith("evals/") or "__pycache__" in rel or arq.suffix == ".pyc":
                continue
            try:
                texto = arq.read_bytes().decode("utf-8")
            except UnicodeDecodeError:
                continue
            achados += [(rel, rotulo, m.group(0)[:60]) for rotulo, rx in PADROES.items() for m in rx.finditer(texto)]
        self.assertEqual(achados, [])


if __name__ == "__main__":
    unittest.main()
