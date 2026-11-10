"""Medidor de gasto (1.7.11): `scripts/medir_gasto.py`.

Transcrições fictícias em pasta temporária: a mesma `message.id` em várias linhas conta uma vez (a última linha
legível), `usage` ausente ou malformado nunca vira zero, o tamanho dos resultados de ferramenta sai por nome (ligando o
`tool_use_id` ao `tool_use`), linha que não é JSON e arquivo ausente viram contagem de "não lido", e nenhum texto de
mensagem aparece na saída.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import SCRIPTS

sys.path.insert(0, str(SCRIPTS))
import medir_gasto  # noqa: E402

CANARIO = "SEGREDO-CANARIO-NAO-IMPRIMIR"


def _usage(i=0, o=0, cl=0, cc=0):
    return {"input_tokens": i, "output_tokens": o, "cache_read_input_tokens": cl, "cache_creation_input_tokens": cc}


def _assistente(mid, modelo="modelo-a", usage=None, blocos=None):
    msg = {"role": "assistant", "id": mid, "model": modelo, "content": blocos or [{"type": "text", "text": CANARIO}]}
    if usage is not None:
        msg["usage"] = usage
    return {"type": "assistant", "message": msg}


def _uso(tid, nome, entrada=None):
    return {"type": "tool_use", "id": tid, "name": nome, "input": entrada or {}}


def _resultado(tid, conteudo):
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tid, "content": conteudo}]}}


def _gravar(pasta: Path, nome: str, linhas) -> Path:
    caminho = pasta / nome
    partes = [l if isinstance(l, str) else json.dumps(l) for l in linhas]
    caminho.write_bytes(("\n".join(partes) + "\n").encode("utf-8"))
    return caminho


class MedirGastoTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_mesma_message_id_em_varias_linhas_conta_uma_vez(self):
        arq = _gravar(self.pasta, "a.jsonl", [
            _assistente("m1", usage=_usage(10, 5, 100, 20), blocos=[{"type": "thinking", "thinking": "x"}]),
            _assistente("m1", usage=_usage(10, 5, 100, 20), blocos=[{"type": "text", "text": "y"}]),
            _assistente("m1", usage=_usage(10, 9, 100, 20), blocos=[_uso("t1", "Bash")]),
            _assistente("m2", "modelo-b", _usage(1, 2, 3, 4)),
        ])
        r = medir_gasto.medir([arq])
        self.assertEqual(r["tokens"]["respostas_contadas"], 2)
        # a última linha legível de m1 vale (saída 9, não 5+5+9)
        self.assertEqual(r["tokens"]["total"], {"entrada": 11, "saida": 11, "cache_lido": 103, "cache_criado": 24})
        self.assertEqual(r["tokens"]["por_modelo"]["modelo-a"]["saida"], 9)
        self.assertEqual(r["tokens"]["por_modelo"]["modelo-b"]["respostas"], 1)
        self.assertEqual(r["tokens"]["por_arquivo"]["a.jsonl"]["respostas"], 2)

    def test_usage_ausente_ou_malformado_nao_vira_zero(self):
        arq = _gravar(self.pasta, "a.jsonl", [
            _assistente("sem"),
            _assistente("faltando", usage={"input_tokens": 5, "output_tokens": 1}),
            _assistente("texto", usage=_usage(i=1) | {"output_tokens": "9"}),
            _assistente("negativo", usage=_usage(i=-1)),
            _assistente("bool", usage=_usage() | {"input_tokens": True}),
            _assistente("ok", usage=_usage(2, 3, 4, 5)),
            _assistente("ok2", usage=_usage(1, 1, 1, 1)),
            _assistente("ok2"),  # linha posterior sem usage não apaga a leitura boa
        ])
        r = medir_gasto.medir([arq])
        self.assertEqual(r["nao_lido"]["resposta_sem_usage_legivel"], 5)
        self.assertEqual(r["tokens"]["respostas_contadas"], 2)
        self.assertEqual(r["tokens"]["total"], {"entrada": 3, "saida": 4, "cache_lido": 5, "cache_criado": 6})

    def test_resposta_sem_message_id_vai_para_nao_lido(self):
        linha = _assistente("x", usage=_usage(1, 1, 1, 1))
        del linha["message"]["id"]
        r = medir_gasto.medir([_gravar(self.pasta, "a.jsonl", [linha])])
        self.assertEqual(r["nao_lido"]["resposta_sem_message_id"], 1)
        self.assertEqual(r["tokens"]["respostas_contadas"], 0)

    def test_linhas_api_request_repetem_mensagens_e_nao_contam(self):
        copia = {"type": "api-request-blob", "message": {"role": "assistant", "content": [_uso("t1", "Bash")]}}
        copia_user = {"type": "api-request-blob", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "x" * 50}]}}
        r = medir_gasto.medir([_gravar(self.pasta, "a.jsonl", [copia, copia_user])])
        self.assertEqual(r["nao_lido"]["resposta_sem_message_id"], 0)
        self.assertEqual(r["resultados_de_ferramenta"]["caracteres_total"], 0)

    def test_dois_arquivos_somam_sem_contar_a_mesma_resposta_duas_vezes(self):
        a = _gravar(self.pasta, "a.jsonl", [_assistente("m1", usage=_usage(1, 1, 1, 1)),
                                            _assistente("m2", usage=_usage(2, 2, 2, 2))])
        b = _gravar(self.pasta, "b.output", [_assistente("m2", usage=_usage(2, 2, 2, 2)),
                                             _assistente("m3", usage=_usage(4, 4, 4, 4))])
        r = medir_gasto.medir([a, b])
        self.assertEqual(r["tokens"]["respostas_contadas"], 3)
        self.assertEqual(r["tokens"]["total"]["entrada"], 7)
        soma_arquivos = sum(v["entrada"] for v in r["tokens"]["por_arquivo"].values())
        self.assertEqual(soma_arquivos, 7)

    def test_resultados_de_ferramenta_por_nome_e_bash_por_comando(self):
        arq = _gravar(self.pasta, "a.jsonl", [
            _assistente("m1", usage=_usage(), blocos=[
                _uso("t1", "Bash", {"command": "cd /x/y && gh api repos/o/r/contents/z -H 'A: b'"}),
                _uso("t2", "Read", {"file_path": "/segredo/caminho"}),
                _uso("t3", "Bash", {"command": "(cd 'pasta' && git -C pasta status)"}),
                _uso("t4", "Bash", {"command": "FOO=1 /usr/bin/python3 -B -m unittest"}),
            ]),
            _resultado("t1", "a" * 100),
            _resultado("t2", [{"type": "text", "text": "b" * 40}, {"type": "image", "source": {}}]),
            _resultado("t3", "c" * 10),
            _resultado("t4", "d" * 5),
            _resultado("t4", "d" * 5),  # repetição do mesmo resultado não conta duas vezes
            _resultado("desconhecido", "e" * 7),
        ])
        r = medir_gasto.medir([arq])["resultados_de_ferramenta"]
        self.assertEqual(r["por_ferramenta"]["Bash"], {"resultados": 3, "caracteres": 115, "maior": 100})
        self.assertEqual(r["por_ferramenta"]["Read"]["caracteres"], 40)
        self.assertEqual(r["por_ferramenta"]["(sem nome)"]["caracteres"], 7)
        self.assertEqual(r["caracteres_total"], 162)
        self.assertEqual(r["bash_por_comando"]["gh api"]["caracteres"], 100)
        self.assertEqual(r["bash_por_comando"]["git"]["caracteres"], 10)
        self.assertEqual(r["bash_por_comando"]["python3"]["caracteres"], 5)
        texto = json.dumps(r)
        self.assertNotIn("segredo", texto)
        self.assertNotIn("repos/o/r", texto)

    def test_categoria_do_comando_pula_cd_e_atribuicao_com_aspas(self):
        c = medir_gasto._comando
        self.assertEqual(c({"command": 'W="E:/a b"; cd "$W/x" && python -B y.py'}), "python")
        self.assertEqual(c({"command": "(cd p && git -C p log | head)"}), "git")
        self.assertEqual(c({"command": "gh api repos/o/r"}), "gh api")
        self.assertEqual(c({"command": "for f in a; do ls; done"}), "for")
        self.assertEqual(c({"command": "$(x)"}), "(outro)")
        self.assertEqual(c({"command": 5}), "(sem comando)")
        self.assertEqual(c(None), "(sem comando)")

    def test_linha_quebrada_campo_ausente_e_arquivo_ausente_nao_quebram(self):
        arq = _gravar(self.pasta, "a.jsonl", [
            "isto não é JSON", "{", "[1, 2]", "null", '{"type": "assistant"}', '{"message": "texto"}',
            '{"type": "user", "message": {"content": [{"type": "tool_result"}]}}',
            '{"type": "user", "message": {"content": "só texto"}}',
            _assistente("ok", usage=_usage(1, 2, 3, 4)),
        ])
        r = medir_gasto.medir([arq, self.pasta / "nao-existe.jsonl"])
        self.assertEqual(r["nao_lido"]["linha_nao_json"], 2)
        self.assertEqual(r["nao_lido"]["resultado_sem_tool_use_id"], 1)
        self.assertEqual(r["nao_lido"]["arquivo_ausente_ou_ilegivel"], 1)
        self.assertEqual(r["tokens"]["total"]["saida"], 2)
        self.assertEqual(r["arquivos"][1]["erro"], "ausente ou ilegível")

    def test_linha_grande_e_descartada_e_contada_sem_perder_as_vizinhas(self):
        arq = self.pasta / "a.jsonl"
        boa1 = json.dumps(_assistente("m1", usage=_usage(1, 1, 1, 1)))
        boa2 = json.dumps(_assistente("m2", usage=_usage(2, 2, 2, 2)))
        arq.write_bytes((boa1 + "\n" + "x" * 5000 + "\n" + boa2 + "\n").encode("utf-8"))
        with mock.patch.object(medir_gasto, "LIMITE_LINHA", 1000):
            r = medir_gasto.medir([arq])
        self.assertEqual(r["nao_lido"]["linha_grande"], 1)
        self.assertEqual(r["tokens"]["respostas_contadas"], 2)
        self.assertEqual(r["arquivos"][0]["linhas"], 3)

    def test_pasta_pega_jsonl_e_output_e_nome_repetido_ganha_sufixo(self):
        (self.pasta / "sub").mkdir()
        _gravar(self.pasta, "a.jsonl", [_assistente("m1", usage=_usage(1, 1, 1, 1))])
        _gravar(self.pasta / "sub", "a.jsonl", [_assistente("m2", usage=_usage(1, 1, 1, 1))])
        _gravar(self.pasta, "b.output", [_assistente("m3", usage=_usage(1, 1, 1, 1))])
        _gravar(self.pasta, "c.txt", [_assistente("m4", usage=_usage(1, 1, 1, 1))])
        (self.pasta / "vazio.output").write_bytes(b"")
        r = medir_gasto.medir([self.pasta])
        self.assertEqual(r["tokens"]["respostas_contadas"], 3)
        nomes = sorted(i["arquivo"] for i in r["arquivos"])
        self.assertEqual(nomes, ["a.jsonl", "a.jsonl#2", "b.output", "vazio.output"])

    def test_saida_nao_traz_texto_de_mensagem_nem_caminho(self):
        arq = _gravar(self.pasta, "a.jsonl", [
            _assistente("m1", usage=_usage(1, 1, 1, 1), blocos=[
                {"type": "text", "text": CANARIO}, _uso("t1", "Bash", {"command": f"echo {CANARIO}"})]),
            _resultado("t1", CANARIO * 3),
        ])
        saida = self.pasta / "r.json"
        proc = subprocess.run([sys.executable, "-I", "-B", str(SCRIPTS / "medir_gasto.py"), str(arq)],
                              capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn(CANARIO, proc.stdout)
        self.assertNotIn(self._tmp.name, proc.stdout)
        self.assertEqual(json.loads(proc.stdout)["resultados_de_ferramenta"]["bash_por_comando"]["echo"]["caracteres"],
                         len(CANARIO) * 3)
        proc = subprocess.run([sys.executable, "-I", "-B", str(SCRIPTS / "medir_gasto.py"), str(arq),
                               "--saida", str(saida)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "")
        dados = saida.read_bytes()
        self.assertNotIn(b"\r\n", dados)
        self.assertNotIn(CANARIO.encode(), dados)
        self.assertEqual(json.loads(dados)["tokens"]["total"]["entrada"], 1)


if __name__ == "__main__":
    unittest.main()
