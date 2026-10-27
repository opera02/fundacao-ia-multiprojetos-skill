"""P7 local: dados fictícios, validação estrita e nenhum modelo ou CLI externa."""
from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

MODULO = Path(__file__).resolve().parents[2] / "fundacao-ia-multiprojetos/evals/juiz_codex.py"


def gravar(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestJuizLocal(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MODULO.is_file(), "P7 ausente: preparar/validar/comparar localmente ainda não implementados")
        spec = importlib.util.spec_from_file_location("juiz_local_p7", MODULO)
        self.j = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.j)
        td = tempfile.TemporaryDirectory(prefix="juiz-ficticio-")
        self.addCleanup(td.cleanup)
        self.t = Path(td.name).resolve()
        self.cega = self.t / "fonte-cega"
        self.cega.mkdir()
        self.folha = {}
        for ident in ("13-A", "13-B"):
            self.folha[ident] = {"avaliacao": 13, "expectations": [
                {"text": "Apresenta evidência verificável.", "passed": None, "evidence": ""},
                {"text": "Declara as limitações.", "passed": None, "evidence": ""}]}
            saidas = self.cega / ident / "saidas"
            saidas.mkdir(parents=True)
            (saidas / "nome-original-do-braco.md").write_text("Resposta fictícia.\n", encoding="utf-8")
            # Não é texto UTF-8: tentar decodificar fatos invalida um preparo que deveria funcionar.
            (saidas.parent / "fatos.json").write_bytes(b"\xffFATOS-PRIVADOS")
        gravar(self.cega / "notas.json", self.folha)
        self.dest = self.t / "entrega-neutra"

    def preparar(self):
        return self.j.preparar(self.cega, self.dest, "modelo-ficticio", "esforco-ficticio")

    def notas(self, nome, passed=(True, False, "nao_medido", True)):
        pacote = json.loads((self.dest / "pacote.json").read_text(encoding="utf-8"))
        valores = iter(passed)
        dados = {"formato": "fundacao.juiz.notas/1", "pacote_sha256": sha(self.dest / "pacote.json"), "notas": [
            {"id": caso["id"], "expectations": [
                {"text": texto, "passed": next(valores), "evidence": "Conferência fictícia no documento."}
                for texto in caso["rubrica"]]} for caso in pacote["casos"]]}
        path = self.t / nome
        gravar(path, dados)
        return path, dados

    def test_preparo_neutraliza_nomes_preserva_rubrica_e_nao_autoriza_execucao(self):
        antes = {p: p.read_bytes() for p in self.cega.rglob("*") if p.is_file()}
        r = self.preparar()
        self.assertEqual(set(p.name for p in self.dest.iterdir()), {"pacote.json", "plano.json", "schema.json", "prompt.md"})
        pacote = json.loads((self.dest / "pacote.json").read_text(encoding="utf-8"))
        self.assertEqual([c["id"] for c in pacote["casos"]], ["caso-001", "caso-002"])
        self.assertEqual(pacote["casos"][0]["rubrica"], ["Apresenta evidência verificável.", "Declara as limitações."])
        self.assertEqual(pacote["casos"][0]["documentos"], [{"id": "documento-001", "texto": "Resposta fictícia.\n"}])
        texto = " ".join(p.read_text(encoding="utf-8") for p in self.dest.iterdir())
        for proibido in ("13-A", "13-B", "nome-original", "FATOS-PRIVADOS", str(self.cega), "avaliacao"):
            self.assertNotIn(proibido, texto)
        plano = json.loads((self.dest / "plano.json").read_text(encoding="utf-8"))
        self.assertEqual(plano["autorizacao"], {"estado": "nao_autorizado", "teto_chamadas": None, "teto_financeiro": None})
        self.assertEqual(plano["consumo"], {"chamadas_reais": "nao_medido", "custo": "nao_medido"})
        self.assertEqual(plano["modelo_proposto"], "modelo-ficticio")
        self.assertEqual(plano["esforco_proposto"], "esforco-ficticio")
        self.assertEqual(r["pacote_sha256"], sha(self.dest / "pacote.json"))
        self.assertEqual(antes, {p: p.read_bytes() for p in self.cega.rglob("*") if p.is_file()})

    def test_folha_parcial_preenchida_ou_com_metadados_recusa_sem_gravar(self):
        mutacoes = [lambda f: f["13-A"]["expectations"][0].update(passed=False),
                    lambda f: f["13-A"]["expectations"][0].update(passed="nao_medido"),
                    lambda f: f["13-A"]["expectations"][0].update(evidence="nota anterior"),
                    lambda f: f["13-A"].update(origem="braço"),
                    lambda f: f["13-A"].update(avaliacao=True),
                    lambda f: f["13-B"]["expectations"][0].update(text="Rubrica de outro braço.")]
        for mudar in mutacoes:
            with self.subTest(mudar=mudar):
                folha = copy.deepcopy(self.folha)
                mudar(folha)
                gravar(self.cega / "notas.json", folha)
                with self.assertRaises(self.j.Recusa):
                    self.preparar()
                self.assertFalse(self.dest.exists())

    def test_entrada_com_json_duplicado_e_rubrica_vazia_recusa(self):
        path = self.cega / "notas.json"
        original = path.read_text(encoding="utf-8")
        for texto in (original.replace('"avaliacao": 13', '"avaliacao": 13, "avaliacao": 13', 1),
                      original.replace('"Apresenta evidência verificável."', '" "', 1)):
            path.write_text(texto, encoding="utf-8")
            with self.assertRaises(self.j.Recusa):
                self.preparar()
            self.assertFalse(self.dest.exists())

    def test_arquivos_inesperados_e_saida_binaria_nao_entram_no_pacote(self):
        intrusos = [self.cega / "mapa.json", self.cega / "13-A" / "grading.json",
                    self.cega / "13-A/saidas/trace.jsonl", self.cega / "13-A/saidas/resposta.bin"]
        for path in intrusos:
            with self.subTest(path=path.name):
                path.write_text("metadado privado", encoding="utf-8")
                with self.assertRaises(self.j.Recusa):
                    self.preparar()
                self.assertFalse(self.dest.exists())
                path.unlink()
        (self.cega / "13-A/saidas/nome-original-do-braco.md").write_bytes(b"\xff\x00")
        with self.assertRaises(self.j.Recusa):
            self.preparar()
        self.assertFalse(self.dest.exists())

    def test_pasta_nao_vazia_e_preparo_repetido_preservam_arquivos(self):
        self.dest.mkdir()
        sentinela = self.dest / "preservar.txt"
        sentinela.write_bytes(b"preservar")
        with self.assertRaises(self.j.Recusa):
            self.preparar()
        self.assertEqual(sentinela.read_bytes(), b"preservar")
        sentinela.unlink()
        self.preparar()
        antes = {p.name: p.read_bytes() for p in self.dest.iterdir()}
        with self.assertRaises(self.j.Recusa):
            self.preparar()
        self.assertEqual(antes, {p.name: p.read_bytes() for p in self.dest.iterdir()})

    def test_destino_sobreposto_e_propostas_ausentes_recusam(self):
        for destino in (self.cega / "nova", self.cega, self.t):
            with self.subTest(destino=destino.name), self.assertRaises(self.j.Recusa):
                self.j.preparar(self.cega, destino, "modelo", "esforco")
        for modelo, esforco in (("", "alto"), ("modelo", " "), (None, "alto")):
            with self.subTest(modelo=modelo), self.assertRaises(self.j.Recusa):
                self.j.preparar(self.cega, self.dest, modelo, esforco)
        self.assertFalse(self.dest.exists())

    def test_hardlinks_na_entrada_recusam_sem_ler_ou_sobrescrever(self):
        original = self.cega / "13-A/saidas/nome-original-do-braco.md"
        alvo = self.t / "compartilhado.md"
        original.rename(alvo)
        os.link(alvo, original)
        with self.assertRaises(self.j.Recusa):
            self.preparar()
        self.assertFalse(self.dest.exists())
        self.assertEqual(alvo.read_text(encoding="utf-8"), "Resposta fictícia.\n")

    def test_ligacao_em_ancestral_de_entrada_e_destino_recusa(self):
        real = self.t / "real"
        real.mkdir()
        elo = self.t / "elo"
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(real), str(elo))
        else:
            elo.symlink_to(real, target_is_directory=True)
        self.addCleanup(lambda: elo.rmdir() if os.name == "nt" else elo.unlink())
        for destino in (elo / "pacote",):
            with self.assertRaises(self.j.Recusa):
                self.j.preparar(self.cega, destino, "modelo", "alto")
        self.cega.rename(real / "fonte")
        with self.assertRaises(self.j.Recusa):
            self.j.preparar(elo / "fonte", self.dest, "modelo", "alto")
        self.assertFalse(self.dest.exists())
        self.assertEqual(list(real.iterdir()), [real / "fonte"])

    def test_validacao_conta_booleanos_e_ausencias_sem_custo_inventado(self):
        self.preparar()
        path, _ = self.notas("juiz.json")
        r = self.j.validar(self.dest, path)
        self.assertTrue(r["valido"])
        self.assertEqual((r["criterios"], r["medidos"], r["nao_medidos"]), (4, 3, 1))
        self.assertEqual(r["notas_sha256"], sha(path))
        self.assertNotIn("custo", r)

    def test_envelope_ordem_ids_rubrica_e_evidencia_sao_estritos(self):
        self.preparar()
        path, base = self.notas("juiz.json")
        mutacoes = [lambda n: n.update(extra="privado"), lambda n: n.update(formato="outro"),
                    lambda n: n.update(pacote_sha256="0" * 64), lambda n: n["notas"].reverse(),
                    lambda n: n["notas"].append(copy.deepcopy(n["notas"][0])),
                    lambda n: n["notas"][0].update(id="13-A"),
                    lambda n: n["notas"][0].update(extra=1),
                    lambda n: n["notas"][0]["expectations"].reverse(),
                    lambda n: n["notas"][0]["expectations"][0].update(text="mudou"),
                    lambda n: n["notas"][0]["expectations"][0].update(extra=True)]
        for mudar in mutacoes:
            with self.subTest(mudar=mudar):
                dados = copy.deepcopy(base)
                mudar(dados)
                gravar(path, dados)
                with self.assertRaises(self.j.Recusa):
                    self.j.validar(self.dest, path)
        for valor in (None, 0, 1, 0.0, 1.0, "true", "false", "nao medido", [], {}):
            dados = copy.deepcopy(base)
            dados["notas"][0]["expectations"][0]["passed"] = valor
            gravar(path, dados)
            with self.subTest(passed=valor), self.assertRaises(self.j.Recusa):
                self.j.validar(self.dest, path)
        for valor in ("", "   ", None, 1):
            dados = copy.deepcopy(base)
            dados["notas"][0]["expectations"][0]["evidence"] = valor
            gravar(path, dados)
            with self.subTest(evidence=valor), self.assertRaises(self.j.Recusa):
                self.j.validar(self.dest, path)

    def test_json_duplicado_e_nao_finito_nas_notas_recusam(self):
        self.preparar()
        path, _ = self.notas("juiz.json")
        original = path.read_text(encoding="utf-8")
        for texto in (original.replace('"passed": true', '"passed": true, "passed": false', 1),
                      original.replace('"passed": true', '"passed": NaN', 1)):
            path.write_text(texto, encoding="utf-8")
            with self.assertRaises(self.j.Recusa):
                self.j.validar(self.dest, path)

    def test_inteiro_json_acima_do_limite_e_recusado_sem_erro_do_parser(self):
        self.preparar()
        path, _ = self.notas("juiz.json")
        original = path.read_text(encoding="utf-8")
        # O decodificador do Python pode recusar antes de chegar à validação da nota.
        import sys
        limite = getattr(sys, "get_int_max_str_digits", lambda: 0)()
        numero = "9" * ((limite + 1) if limite else 10000)
        path.write_text(original.replace('"passed": true', '"passed": ' + numero, 1), encoding="utf-8")
        with self.assertRaises(ValueError) as erro:
            self.j.validar(self.dest, path)
        self.assertIsInstance(erro.exception, self.j.Recusa, "erro interno do parser escapou do contrato")

    def limites_presentes(self):
        for nome in ("MAX_ARQUIVO_BYTES", "MAX_TOTAL_BYTES", "MAX_ARQUIVOS", "MAX_ENTRADAS",
                     "MAX_PROFUNDIDADE", "MAX_CASOS", "MAX_CRITERIOS", "MAX_AGREGADO_BYTES"):
            self.assertTrue(hasattr(self.j, nome), "limites locais ausentes: " + nome)

    def test_arquivo_grande_recusa_pelo_stat_antes_de_abrir(self):
        self.limites_presentes()
        from unittest import mock
        alvo = self.cega / "13-A/saidas/nome-original-do-braco.md"
        with alvo.open("wb") as f:
            f.truncate(self.j.MAX_ARQUIVO_BYTES + 1)
        with mock.patch.object(self.j.os, "open", wraps=os.open) as abrir:
            with self.assertRaises(self.j.Recusa):
                self.preparar()
        self.assertNotIn(alvo, [Path(c.args[0]) for c in abrir.call_args_list])
        self.assertFalse(self.dest.exists())

    def test_crescimento_durante_leitura_usa_teto_mais_um(self):
        self.limites_presentes()
        from unittest import mock
        alvo = self.t / "crescente.txt"
        alvo.write_bytes(b"curto")
        fdopen_real = os.fdopen
        teste = self

        class Crescente:
            def __init__(self, fd, modo):
                self.real = fdopen_real(fd, modo)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.real.close()

            def fileno(self):
                return self.real.fileno()

            def read(self, quantidade=-1):
                teste.assertEqual(quantidade, 17, "leitura sem limite consumiria o crescimento inteiro")
                with alvo.open("ab") as f:
                    f.write(b"x" * 200)
                return self.real.read(quantidade)

        with mock.patch.object(self.j.os, "fdopen", side_effect=Crescente):
            with self.assertRaises(self.j.Recusa):
                self.j._ler_bytes(alvo, limite=16)

    def test_total_quantidade_e_profundidade_recusam_antes_de_gravar(self):
        self.limites_presentes()
        from unittest import mock
        for ident in self.folha:
            (self.cega / ident / "saidas/nome-original-do-braco.md").write_bytes(b"12345678")
        extra = self.cega / "13-B/saidas/mais.txt"
        extra.write_bytes(b"x")
        with mock.patch.object(self.j, "MAX_TOTAL_BYTES", 16):
            with self.assertRaises(self.j.Recusa):
                self.preparar()
        extra.unlink()
        with mock.patch.object(self.j, "MAX_ARQUIVOS", 1):
            with self.assertRaises(self.j.Recusa):
                self.preparar()
        with mock.patch.object(self.j, "MAX_ENTRADAS", 1):
            with self.assertRaises(self.j.Recusa):
                self.preparar()
        pasta = self.cega / "13-A/saidas"
        for _ in range(self.j.MAX_PROFUNDIDADE + 1):
            pasta = pasta / "nivel"
            pasta.mkdir()
        (pasta / "texto.txt").write_bytes(b"x")
        with self.assertRaises(self.j.Recusa):
            self.preparar()
        self.assertFalse(self.dest.exists())

    def test_quantidades_de_casos_criterios_e_agregado_tem_limites(self):
        self.limites_presentes()
        from unittest import mock
        for nome, teto in (("MAX_CASOS", 1), ("MAX_CRITERIOS", 1), ("MAX_AGREGADO_BYTES", 16)):
            with self.subTest(limite=nome), mock.patch.object(self.j, nome, teto):
                with self.assertRaises(self.j.Recusa):
                    self.preparar()
                self.assertFalse(self.dest.exists())

    def test_hash_dos_artefatos_do_pacote_e_conferido(self):
        self.preparar()
        path, _ = self.notas("juiz.json")
        for nome in ("pacote.json", "prompt.md", "schema.json"):
            artefato = self.dest / nome
            antes = artefato.read_bytes()
            artefato.write_bytes(antes + b" ")
            with self.subTest(artefato=nome), self.assertRaises(self.j.Recusa):
                self.j.validar(self.dest, path)
            artefato.write_bytes(antes)
        plano = json.loads((self.dest / "plano.json").read_text(encoding="utf-8"))
        plano["autorizacao"]["teto_chamadas"] = 0
        gravar(self.dest / "plano.json", plano)
        with self.assertRaises(self.j.Recusa):
            self.j.validar(self.dest, path)

    def test_comparacao_manual_um_de_dois_e_ausencias_separadas(self):
        self.preparar()
        juiz, _ = self.notas("juiz.json", (True, False, "nao_medido", True))
        coord, _ = self.notas("coord.json", (True, True, False, "nao_medido"))
        r = self.j.comparar(self.dest, juiz, coord)
        self.assertEqual((r["total"], r["denominador"], r["concordantes"], r["discordantes"]), (4, 2, 1, 1))
        self.assertEqual(r["taxa"], 0.5)
        self.assertEqual(r["estado"], "medido")
        self.assertEqual(r["nao_medidos"], [
            {"id": "caso-002", "criterio": 1, "juiz": "nao_medido", "coordenador": False},
            {"id": "caso-002", "criterio": 2, "juiz": True, "coordenador": "nao_medido"}])
        self.assertEqual(r["juiz_sha256"], sha(juiz))
        self.assertEqual(r["coordenador_sha256"], sha(coord))
        self.assertEqual(r["plano_sha256"], sha(self.dest / "plano.json"))
        self.assertEqual(len(list(self.dest.iterdir())), 4, "a comparação alterou o pacote")

    def test_denominador_vazio_mantem_taxa_null_e_nao_medido(self):
        self.preparar()
        juiz, _ = self.notas("juiz.json", ("nao_medido",) * 4)
        coord, _ = self.notas("coord.json", (True, False, True, False))
        r = self.j.comparar(self.dest, juiz, coord)
        self.assertEqual(r["denominador"], 0)
        self.assertIsNone(r["taxa"])
        self.assertEqual(r["estado"], "nao_medido")
        self.assertEqual(len(r["nao_medidos"]), 4)

    def test_cli_local_grava_recibo_exclusivo_e_rejeita_executar(self):
        def cli(*args):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                try:
                    return self.j.main(list(map(str, args)))
                except SystemExit as exc:
                    return exc.code
        self.assertEqual(cli("preparar", "--cega", self.cega, "--destino", self.dest,
                             "--modelo", "modelo", "--esforco", "alto", "--executar"), 2)
        self.assertFalse(self.dest.exists())
        self.assertEqual(cli("preparar", "--cega", self.cega, "--destino", self.dest,
                             "--modelo", "modelo", "--esforco", "alto"), 0)
        juiz, _ = self.notas("juiz.json")
        coord, _ = self.notas("coord.json")
        recibo = self.t / "recibo.json"
        self.assertEqual(cli("comparar", "--pacote", self.dest, "--juiz", juiz, "--coordenador", coord,
                             "--recibo", recibo), 0)
        antes = recibo.read_bytes()
        self.assertEqual(cli("comparar", "--pacote", self.dest, "--juiz", juiz, "--coordenador", coord,
                             "--recibo", recibo), 3)
        self.assertEqual(recibo.read_bytes(), antes)
        validacao = self.t / "validacao.json"
        self.assertEqual(cli("validar", "--pacote", self.dest, "--notas", juiz, "--recibo", validacao), 0)
        self.assertTrue(json.loads(validacao.read_text(encoding="utf-8"))["valido"])
        alvo = self.t / "alvo.json"
        alvo.write_bytes(b"preservar")
        vinculo = self.t / "vinculo.json"
        os.link(alvo, vinculo)
        self.assertEqual(cli("validar", "--pacote", self.dest, "--notas", juiz, "--recibo", vinculo), 3)
        self.assertEqual(alvo.read_bytes(), b"preservar")


if __name__ == "__main__":
    unittest.main()
