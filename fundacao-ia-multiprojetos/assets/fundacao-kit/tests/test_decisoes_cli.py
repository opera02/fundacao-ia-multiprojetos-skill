"""CLI das decisões: `python -m fundacao decisao preparar|verificar|registrar|conferir-ancora|comando`.

A CLI roda no próprio processo, com a âncora de ENSAIO no lugar da âncora padrão desta máquina (assim o teste
não depende da âncora real nem a toca). O registro `projects/<p>/decisoes/registro.jsonl` mantém o formato da
ferramenta da fundação: as decisões já registradas lá continuam valendo, e registrar de novo responde
"já registrada".
"""

from __future__ import annotations

import io
import json
import os
import shutil
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from helpers import FoundationTestCase
from apoio_decisoes import Chaves

from fundacao.__main__ import main
from fundacao.core import decisoes, events
from fundacao.core.auth import ENV_PRINCIPAL
from fundacao.core.tasks import Coordinator

# Os da ferramenta da fundação e, desde a 1.7.4, a data de preparo (avaliação E11, F-02); a decisão que cita outra
# leva também `anterior_sha256` (test_avaliacao_e11_ordem_decisoes).
CAMPOS_DO_REGISTRO = {"decisao_id", "entrega", "impressao_digital", "preparado_em", "registrado_em", "registrado_por",
                      "sha256_assinatura", "sha256_decisao", "task_id", "tipo"}


class DecisoesCliCase(FoundationTestCase):
    def setUp(self):
        super().setUp()
        self.base_chaves = self.root.parent / (self.root.name + "-chaves")
        self.chaves = Chaves(self.base_chaves, principal="operador-lab")
        padrao = mock.patch.object(decisoes, "ANCORAS_PADRAO", (str(self.chaves.ancora),))
        padrao.start()
        self.addCleanup(padrao.stop)
        self.pasta = self.root / "projects" / "juridico-lab"
        (self.pasta / "outputs" / "entrega.md").write_text("Entrega de ensaio (fictícia).\n", encoding="utf-8")
        self.tarefa = Coordinator(self.root, self.con, self.admin, "juridico-lab").create_task("entrega de ensaio")

    def tearDown(self):
        super().tearDown()
        shutil.rmtree(self.base_chaves, ignore_errors=True)

    def cli(self, quem, *args) -> tuple[int, dict | None, str]:
        saida, erro = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {}), redirect_stdout(saida), redirect_stderr(erro):
            os.environ.pop(ENV_PRINCIPAL, None)
            if quem:
                os.environ[ENV_PRINCIPAL] = quem
            codigo = main(["--raiz", str(self.root), *args])
        texto = saida.getvalue()
        return codigo, (json.loads(texto) if texto.strip() else None), erro.getvalue()

    def preparar(self, quem="operador-lab", tipo="aceite", entrega="outputs/entrega.md", tarefa=None, *extra):
        return self.cli(quem, "decisao", "preparar", "--projeto", "juridico-lab", "--tarefa", tarefa or self.tarefa,
                        "--entrega", entrega, "--tipo", tipo, "--motivo", "Aceito a entrega de ensaio.", *extra)

    def preparada(self, tipo="aceite", *extra) -> Path:
        codigo, r, erro = self.preparar("operador-lab", tipo, "outputs/entrega.md", None, *extra)
        self.assertEqual(codigo, 0, erro)
        return Path(r["decisao"])

    def registro(self) -> list[dict]:
        return decisoes.ler_registro(self.pasta / "decisoes" / "registro.jsonl")

    def eventos(self, kind: str) -> int:
        return events.count(self.con, kind, project_id="juridico-lab")


class TestPrepararDecisao(DecisoesCliCase):
    def test_preparar_grava_a_decisao_canonica_e_devolve_o_comando_do_titular(self):
        codigo, r, erro = self.preparar()
        self.assertEqual(codigo, 0, erro)
        arq = Path(r["decisao"])
        self.assertEqual(arq.parent, (self.pasta / "decisoes").resolve())
        d = json.loads(arq.read_text(encoding="utf-8"))
        self.assertEqual(arq.read_bytes(), decisoes.canonico(d))
        self.assertEqual(r["sha256_decisao"], decisoes.sha256_arquivo(arq))
        self.assertEqual((d["assinante"], d["task_id"], d["tipo"], d["entrega"]["caminho"]),
                         ("operador-lab", self.tarefa, "aceite", "outputs/entrega.md"))
        self.assertTrue(r["assinatura_exigida"])
        titular = r["para_o_titular"]
        self.assertEqual(titular["shell"], decisoes.shell_padrao())
        self.assertIn(arq.name, titular["assinar"])
        self.assertEqual(self.eventos("decisao_preparada"), 1)

    def test_preparar_pede_o_shell_do_titular(self):
        codigo, r, erro = self.preparar("operador-lab", "aceite", "outputs/entrega.md", None, "--shell", "bash")
        self.assertEqual(codigo, 0, erro)
        self.assertEqual(r["para_o_titular"]["shell"], "bash")
        self.assertNotIn(chr(92), r["para_o_titular"]["assinar"])

    def test_preparar_recusa_tarefa_alheia_entrega_fora_de_outputs_e_sobrescrita(self):
        alheia = Coordinator(self.root, self.con, self.admin, "reversa-lab").create_task("tarefa de outro projeto")
        (self.pasta / "data" / "x.md").write_text("dado\n", encoding="utf-8")
        for tarefa, entrega, codigo_erro in ((alheia, "outputs/entrega.md", "E_NOT_FOUND"),
                                             (None, "data/x.md", "E_PATH_ESCAPE"),
                                             (None, "outputs/nao-existe.md", "E_NOT_FOUND")):
            with self.subTest(entrega=entrega):
                codigo, r, erro = self.preparar("operador-lab", "aceite", entrega, tarefa)
                self.assertEqual(codigo, 2, r)
                self.assertIn(codigo_erro, erro)
        self.assertFalse(any((self.pasta / "decisoes").glob("*.json")) if (self.pasta / "decisoes").exists() else False)
        codigo, _r, _ = self.preparar("operador-lab", "aceite", "outputs/entrega.md", None, "--decisao-id", "dec-fixa")
        self.assertEqual(codigo, 0)
        antes = (self.pasta / "decisoes" / "dec-fixa.json").read_bytes()
        codigo, _r, erro = self.preparar("operador-lab", "rejeicao", "outputs/entrega.md", None, "--decisao-id", "dec-fixa")
        self.assertEqual(codigo, 2)
        self.assertIn("E_EXISTS", erro)
        self.assertEqual((self.pasta / "decisoes" / "dec-fixa.json").read_bytes(), antes)

    def test_duas_decisoes_no_mesmo_segundo_ganham_identificadores_distintos(self):
        with mock.patch.object(decisoes.time, "strftime", return_value="20261021T010101"):
            primeira, segunda = self.preparada(), self.preparada()
        self.assertEqual((primeira.name, segunda.name), ("dec-aceite-20261021T010101.json",
                                                         "dec-aceite-20261021T010101-2.json"))
        self.assertTrue(primeira.is_file() and segunda.is_file())

    def test_preparar_exige_escrita_no_projeto(self):
        for quem in ("revisor-juridico", "operador-engenharia", None):
            with self.subTest(quem=quem):
                codigo, _r, erro = self.preparar(quem)
                self.assertEqual(codigo, 2)
                self.assertIn("E_ACCESS_DENIED", erro)
        self.assertFalse((self.pasta / "decisoes").exists() and any((self.pasta / "decisoes").iterdir()))


class TestRegistrarDecisao(DecisoesCliCase):
    def registrar(self, arq: Path, quem="operador-lab", *extra):
        return self.cli(quem, "decisao", "registrar", "--arquivo", str(arq), *extra)

    def test_sem_assinatura_outra_chave_conteudo_alterado_e_outro_namespace_sao_recusados(self):
        casos = {"sem assinatura": (None, None), "outra chave": ("intruso", decisoes.NAMESPACE),
                 "outro namespace": ("titular-ensaio", "outro-uso"), "conteúdo alterado": ("titular-ensaio", None)}
        for nome, (chave, namespace) in casos.items():
            with self.subTest(caso=nome):
                arq = self.preparada("correcao")
                if chave:
                    self.chaves.assinar(arq, chave=chave, namespace=namespace or decisoes.NAMESPACE)
                if nome == "conteúdo alterado":
                    d = json.loads(arq.read_text(encoding="utf-8"))
                    d["tipo"] = "aceite"
                    arq.write_bytes(decisoes.canonico(d))
                for acao in ("verificar", "registrar"):
                    codigo, r, erro = self.cli("operador-lab", "decisao", acao, "--arquivo", str(arq))
                    self.assertEqual(codigo, 3, (acao, r, erro))
                    self.assertFalse(r["valida"])
        self.assertEqual(self.registro(), [])
        self.assertEqual(self.eventos(decisoes.EVENTO_ASSINADA), 0)

    def test_registrar_grava_no_formato_da_fundacao_e_repetir_responde_ja_registrada(self):
        arq = self.preparada()
        self.chaves.assinar(arq)
        codigo, r, erro = self.registrar(arq)
        self.assertEqual(codigo, 0, erro)
        self.assertEqual((r["valida"], r["forca"], r["registro"]), (True, "assinatura", "registrada agora"))
        [linha] = self.registro()
        self.assertEqual(set(linha), CAMPOS_DO_REGISTRO)
        self.assertEqual((linha["sha256_decisao"], linha["registrado_por"], linha["task_id"]),
                         (decisoes.sha256_arquivo(arq), "operador-lab", self.tarefa))
        self.assertEqual(linha["impressao_digital"], decisoes.ler_ancora(self.chaves.ancora)[0]["impressao_digital"])
        self.assertEqual(self.eventos(decisoes.EVENTO_ASSINADA), 1)
        codigo, r, erro = self.registrar(arq)
        self.assertEqual((codigo, r["registro"]), (0, "já registrada"), erro)
        self.assertEqual((len(self.registro()), self.eventos(decisoes.EVENTO_ASSINADA)), (1, 1))

    def test_decisao_registrada_pela_ferramenta_da_fundacao_continua_valida(self):
        # Como a ferramenta da fundação gravava: mesma decisão canônica, linha com os mesmos campos e o mesmo evento.
        arq = self.preparada()
        self.chaves.assinar(arq)
        v = decisoes.verificar_decisao(arq, self.pasta, self.chaves.ancora)
        antiga = {k: v[k] for k in ("decisao_id", "tipo", "task_id", "sha256_decisao", "entrega")}
        antiga.update(impressao_digital=v["assinatura"]["impressao_digital"],
                      sha256_assinatura=v["assinatura"]["sha256_assinatura"],
                      registrado_em="2026-10-20T16:13:46-0300", registrado_por="operador-lab")
        (self.pasta / "decisoes" / "registro.jsonl").write_text(
            json.dumps(antiga, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        events.emit(self.con, decisoes.EVENTO_ASSINADA, project_id="juridico-lab", subject="operador-lab",
                    task_id=self.tarefa, payload={k: antiga[k] for k in (
                        "decisao_id", "tipo", "sha256_decisao", "sha256_assinatura", "impressao_digital")})
        codigo, r, erro = self.cli("operador-lab", "decisao", "verificar", "--arquivo", str(arq))
        self.assertEqual((codigo, r["valida"]), (0, True), erro)
        codigo, r, erro = self.registrar(arq)
        self.assertEqual((codigo, r["registro"]), (0, "já registrada"), erro)
        self.assertEqual(self.registro(), [antiga])

    def test_registro_sem_o_evento_e_completado_sem_duplicar_a_linha(self):
        arq = self.preparada()
        self.chaves.assinar(arq)
        self.assertEqual(self.registrar(arq)[0], 0)
        self.con.execute("DELETE FROM event WHERE kind = ?", (decisoes.EVENTO_ASSINADA,))  # queda antes do evento
        self.con.commit()
        codigo, r, _ = self.registrar(arq)
        self.assertEqual((codigo, r["registro"]), (0, "registrada agora"))
        self.assertEqual((len(self.registro()), self.eventos(decisoes.EVENTO_ASSINADA)), (1, 1))
        (self.pasta / "decisoes" / "registro.jsonl").unlink()  # queda depois do evento, antes da linha
        codigo, r, _ = self.registrar(arq)
        self.assertEqual((codigo, r["registro"]), (0, "registrada agora"))
        self.assertEqual((len(self.registro()), self.eventos(decisoes.EVENTO_ASSINADA)), (1, 1))

    def test_registrar_exige_escrita_e_outra_ancora_e_recusada(self):
        arq = self.preparada()
        self.chaves.assinar(arq)
        codigo, _r, erro = self.registrar(arq, "revisor-juridico")
        self.assertEqual(codigo, 2)
        self.assertIn("E_ACCESS_DENIED", erro)
        outra = Chaves(self.base_chaves / "outra", principal="operador-lab")
        codigo, _r, erro = self.registrar(arq, "operador-lab", "--ancora", str(outra.ancora))
        self.assertEqual(codigo, 2)
        self.assertIn("âncora padrão", erro)
        self.assertEqual(self.registro(), [])

    def test_decisao_fora_de_decisoes_e_recusada_antes_de_ler(self):
        fora = self.pasta / "outputs" / "dec.json"
        fora.write_text("{}", encoding="utf-8")
        codigo, _r, erro = self.cli("operador-lab", "decisao", "verificar", "--arquivo", str(fora))
        self.assertEqual(codigo, 2)
        self.assertIn("decisoes/", erro)

    def test_tipo_dispensado_no_laboratorio_registra_so_com_permissao_de_aprovar(self):
        (self.root / "registry" / decisoes.POLITICA).write_text(json.dumps({
            "schema_version": decisoes.SCHEMA_POLITICA, "tipos": {"correcao": {"exige_assinatura": False}}}),
            encoding="utf-8")
        with mock.patch.object(decisoes, "ANCORAS_PADRAO", (str(self.base_chaves / "nao-existe"),)):
            codigo, r, erro = self.preparar("operador-juridico", "correcao")
            self.assertEqual((codigo, r["assinatura_exigida"]), (0, False), erro)
            codigo, _r, erro = self.registrar(Path(r["decisao"]), "operador-juridico")
            self.assertEqual(codigo, 2)  # escreve no projeto, mas não aprova
            self.assertIn("E_ACCESS_DENIED", erro)
            arq = self.preparada("correcao", "--decisao-id", "dec-do-admin")
            codigo, r, erro = self.registrar(arq, "operador-lab")
            self.assertEqual((codigo, r["forca"], r["registro"]), (0, "sem-assinatura", "registrada agora"), erro)
        [linha] = self.registro()
        self.assertEqual((linha["forca"], linha["impressao_digital"], linha["sha256_assinatura"]),
                         ("sem-assinatura", None, None))
        self.assertEqual(self.eventos(decisoes.EVENTO_SEM_ASSINATURA), 1)


class TestAncoraEComando(DecisoesCliCase):
    def test_conferir_ancora_acusa_ancora_gravavel(self):
        codigo, r, erro = self.cli("operador-lab", "decisao", "conferir-ancora")
        self.assertEqual(codigo, 3, erro)
        self.assertEqual((r["existe"], r["protegida"]), (True, False))

    def test_comando_reimprime_para_o_shell_pedido(self):
        arq = self.preparada()
        codigo, r, erro = self.cli("operador-lab", "decisao", "comando", "--arquivo", str(arq), "--shell", "powershell")
        if os.name == "nt" or os.environ.get("WSL_DISTRO_NAME", "").strip():
            self.assertEqual(codigo, 0, erro)
            self.assertEqual(r["para_o_titular"]["shell"], "powershell")
            self.assertIn(decisoes.caminho_windows(arq), r["para_o_titular"]["assinar"])
        else:  # Linux fora do WSL (a CI pública): o caminho não existe no Windows, e o comando do PowerShell é recusado
            self.assertEqual(codigo, 2, erro)
            self.assertIn("sem equivalente no Windows", erro)
        codigo, r, erro = self.cli("operador-engenharia", "decisao", "comando", "--arquivo", str(arq))
        self.assertEqual(codigo, 2)
        self.assertIn("E_ACCESS_DENIED", erro)



class TestArquivosForaDoFormato(DecisoesCliCase):
    """JSON válido que não é objeto (na decisão ou numa linha do registro) sai pelo contrato da CLI: código 2."""

    def test_decisao_que_nao_e_objeto_no_comando(self):
        arq = self.pasta / "decisoes" / "dec-lista.json"
        arq.parent.mkdir(exist_ok=True)
        arq.write_text("[]", encoding="utf-8")
        codigo, _r, erro = self.cli("operador-lab", "decisao", "comando", "--arquivo", str(arq))
        self.assertEqual(codigo, 2)
        self.assertIn("E_VALIDATION", erro)

    def test_linha_do_registro_que_nao_e_objeto(self):
        arq = self.preparada()
        self.chaves.assinar(arq)
        (self.pasta / "decisoes" / "registro.jsonl").write_text("[1, 2]\n", encoding="utf-8")
        for args in (("decisao", "registrar", "--arquivo", str(arq)), ("tarefa", "concluir", "--decisao", str(arq))):
            with self.subTest(args=args[:2]):
                codigo, _r, erro = self.cli("operador-lab", *args)
                self.assertEqual(codigo, 2, erro)
                self.assertIn("E_VALIDATION", erro)

if __name__ == "__main__":
    import unittest
    unittest.main()
