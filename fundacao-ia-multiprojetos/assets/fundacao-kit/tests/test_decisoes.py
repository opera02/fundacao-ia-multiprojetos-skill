"""Decisões do titular assinadas, no kit (barreira da DECISAO-003 da fundação de referência).

Chave e âncora de ENSAIO geradas no teste, nunca as do titular. Recusas: sem assinatura, outra chave,
conteúdo alterado, outro namespace, assinante que não é o dono da chave, entrega alterada, decisão fora de
`decisoes/` ou de outro projeto e arquivo fora da forma canônica. Formato igual ao das decisões já
registradas pela ferramenta da fundação (`ferramentas/decisao_assinada.py`), para que continuem válidas.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401  (põe o kit no sys.path)
from apoio_decisoes import Chaves, keygen

from fundacao.core import decisoes
from fundacao.core.contracts import FundacaoError


class TestNucleoDecisoes(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="decisoes-"))
        self.chaves = Chaves(self.tmp)
        self.pasta = self.tmp / "projects" / "proj-ensaio"
        (self.pasta / "outputs").mkdir(parents=True)
        (self.pasta / "decisoes").mkdir()
        self.entrega = self.pasta / "outputs" / "entrega-v1.md"
        self.entrega.write_text("Entrega de ensaio, versão 1.\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def decisao(self, *, assinante="titular-ensaio", nome="dec-1", tipo="aceite", projeto="proj-ensaio"):
        d = decisoes.montar_decisao(projeto=projeto, tarefa="task_ensaio", entrega_rel="outputs/entrega-v1.md",
                                    entrega_sha256=decisoes.sha256_arquivo(self.entrega), tipo=tipo,
                                    motivo="Aceito a versão 1.", assinante=assinante, decisao_id=nome,
                                    agora="2026-10-21T01:00:00-0300")
        arq = self.pasta / "decisoes" / f"{nome}.json"
        arq.write_bytes(decisoes.canonico(d))
        return arq

    def verificar(self, arq):
        return decisoes.verificar_decisao(arq, self.pasta, self.chaves.ancora)

    def recusa(self, arq) -> str:
        r = self.verificar(arq)
        self.assertFalse(r["valida"], r)
        return r["motivo"]

    def test_assinatura_do_titular_e_aceita(self):
        arq = self.decisao()
        self.chaves.assinar(arq)
        r = self.verificar(arq)
        self.assertTrue(r["valida"], r)
        self.assertEqual(r["forca"], "assinatura")
        self.assertEqual(r["assinatura"]["impressao_digital"],
                         decisoes.ler_ancora(self.chaves.ancora)[0]["impressao_digital"])
        self.assertEqual((r["tipo"], r["task_id"], r["decisao_id"]), ("aceite", "task_ensaio", "dec-1"))

    def test_sem_assinatura_e_recusada(self):
        self.assertEqual(self.recusa(self.decisao()), "assinatura ausente")

    def test_assinada_por_outra_chave_e_recusada(self):
        arq = self.decisao()
        self.chaves.assinar(arq, chave="intruso")
        self.assertIn("chave que não está na âncora", self.recusa(arq))

    def test_conteudo_alterado_depois_de_assinar_e_recusado(self):
        arq = self.decisao(tipo="correcao")
        self.chaves.assinar(arq)
        d = json.loads(arq.read_text(encoding="utf-8"))
        d["tipo"] = "aceite"
        arq.write_bytes(decisoes.canonico(d))
        self.assertIn("não confere com o conteúdo", self.recusa(arq))

    def test_outro_namespace_e_recusado(self):
        arq = self.decisao()
        self.chaves.assinar(arq, namespace="outro-uso")
        self.assertIn("outro namespace", self.recusa(arq))

    def test_assinante_que_nao_e_o_dono_da_chave_e_recusado(self):
        arq = self.decisao(assinante="outra-pessoa")
        self.chaves.assinar(arq)
        self.assertIn("não é o dono da chave", self.recusa(arq))

    def test_entrega_alterada_depois_da_decisao_e_recusada(self):
        arq = self.decisao()
        self.chaves.assinar(arq)
        self.entrega.write_text("Entrega trocada depois da decisão.\n", encoding="utf-8")
        self.assertEqual(self.recusa(arq), "entrega ausente ou alterada depois da decisão")

    def test_decisao_fora_de_decisoes_e_recusada(self):
        arq = self.decisao()
        self.chaves.assinar(arq)
        fora = self.pasta / "outputs" / "dec-1.json"
        shutil.copy(arq, fora)
        shutil.copy(str(arq) + ".sig", str(fora) + ".sig")
        self.assertEqual(self.recusa(fora), "decisão fora de decisoes/ do projeto")

    def test_decisao_de_outro_projeto_e_recusada(self):
        arq = self.decisao(projeto="outro-projeto")
        self.chaves.assinar(arq)
        self.assertEqual(self.recusa(arq), "decisão de outro projeto")

    def test_arquivo_fora_da_forma_canonica_e_recusado(self):
        arq = self.decisao()
        d = json.loads(arq.read_text(encoding="utf-8"))
        arq.write_text(json.dumps(d), encoding="utf-8")  # JSON compacto, assinado do jeito que está
        self.chaves.assinar(arq)
        self.assertEqual(self.recusa(arq), "decisão fora da forma canônica")

    def test_campo_que_nao_e_texto_fica_fora_do_esquema(self):
        # Assinada como está, mas `task_id`/`assinante` que não são texto chegariam à trilha e ao ssh-keygen.
        for campo, valor in (("task_id", ["task_ensaio"]), ("assinante", 7), ("decisao_id", None)):
            with self.subTest(campo=campo):
                arq = self.decisao()
                d = json.loads(arq.read_text(encoding="utf-8"))
                d[campo] = valor
                arq.write_bytes(decisoes.canonico(d))
                self.chaves.assinar(arq)
                self.assertEqual(self.recusa(arq), "decisão fora do esquema")

    def test_assinatura_e_conferida_sobre_os_bytes_ja_lidos(self):
        # Revisão independente (TOCTOU): trocar a decisão entre a leitura e o ssh-keygen não muda o que é conferido;
        # o resultado descreve os bytes lidos, e as etapas seguintes (registrar, concluir) conferem de novo.
        arq = self.decisao(tipo="correcao")
        self.chaves.assinar(arq)
        lidos = arq.read_bytes()
        rodar = subprocess.run

        def trocar_e_rodar(*args, **kwargs):
            arq.write_bytes(lidos.replace(b'"correcao"', b'"aceite"'))  # no disco, já é outra decisão
            return rodar(*args, **kwargs)

        with mock.patch.object(decisoes.subprocess, "run", side_effect=trocar_e_rodar):
            r = self.verificar(arq)
        self.assertEqual((r["valida"], r["tipo"], r["sha256_decisao"]), (True, "correcao", decisoes.sha256_bytes(lidos)))

    def test_forma_canonica_igual_a_da_ferramenta_da_fundacao(self):
        d = decisoes.montar_decisao(projeto="p", tarefa="t", entrega_rel="outputs/x.md", entrega_sha256="ab",
                                    tipo="aceite", motivo=" aceito; P8 opção b ", assinante="titular-ensaio",
                                    decisao_id="dec-aceite-1", agora="2026-10-20T21:11:27-0300")
        esperado = "\n".join([
            "{",
            '  "assinante": "titular-ensaio",',
            '  "decisao_id": "dec-aceite-1",',
            '  "entrega": {',
            '    "caminho": "outputs/x.md",',
            '    "sha256": "ab"',
            "  },",
            '  "motivo": "aceito; P8 opção b",',
            '  "namespace": "fundacao-decisao",',
            '  "preparado_em": "2026-10-20T21:11:27-0300",',
            '  "project_id": "p",',
            '  "schema_version": "fundacao.decisao_assinada/1",',
            '  "task_id": "t",',
            '  "tipo": "aceite"',
            "}",
            ""])
        self.assertEqual(decisoes.canonico(d), esperado.encode("utf-8"))

    def test_tipo_invalido_motivo_vazio_e_identificador_com_caminho_sao_recusados(self):
        base = dict(projeto="p", tarefa="t", entrega_rel="outputs/x", entrega_sha256="0", assinante="a", agora="x")
        ruins = [("aprovado", "ok", "d"), ("aceite", "  ", "d")]
        ruins += [("aceite", "ok", ruim) for ruim in ("../x", "a/b", r"a\b", "", "dec 1")]
        for tipo, motivo, decisao_id in ruins:
            with self.subTest(tipo=tipo, motivo=motivo, decisao_id=decisao_id):
                with self.assertRaises(ValueError):  # a ferramenta da fundação espera ValueError
                    decisoes.montar_decisao(tipo=tipo, motivo=motivo, decisao_id=decisao_id, **base)
                with self.assertRaises(FundacaoError):  # a CLI do kit responde pelo contrato (código 2)
                    decisoes.montar_decisao(tipo=tipo, motivo=motivo, decisao_id=decisao_id, **base)

    def test_impressao_digital_igual_a_do_ssh_keygen(self):
        saida = subprocess.run([keygen(), "-lf", str(self.chaves.chave()) + ".pub"], check=True,
                               capture_output=True, text=True).stdout
        linha = decisoes.ler_ancora(self.chaves.ancora)[0]
        self.assertIn(linha["impressao_digital"], saida)
        self.assertEqual((linha["principais"], linha["namespaces"]), (["titular-ensaio"], [decisoes.NAMESPACE]))

    def test_ancora_gravavel_e_acusada(self):
        r = decisoes.conferir_ancora(self.chaves.ancora)
        self.assertTrue(r["existe"])
        self.assertFalse(r["protegida"])  # pasta temporária comum: a sondagem precisa acusar
        self.assertEqual([p.name for p in self.chaves.ancora.parent.iterdir()], ["allowed_signers"])  # sonda apagada

    def test_ssh_keygen_falso_no_path_nao_e_usado(self):
        # Um `ssh-keygen` posto antes no PATH que sempre responde 0 aprovaria qualquer assinatura: vale o do sistema.
        falso = self.tmp / "falso"
        falso.mkdir()
        if os.name == "nt":
            (falso / "ssh-keygen.bat").write_text("@exit /b 0\r\n", encoding="ascii")
        else:
            exe = falso / "ssh-keygen"
            exe.write_text("#!/bin/sh\nexit 0\n", encoding="ascii")
            exe.chmod(0o755)
        if not decisoes.ssh_keygen_do_sistema():
            self.skipTest("ssh-keygen do sistema ausente no caminho fixo; vale o do PATH")
        arq = self.decisao(tipo="correcao")
        self.chaves.assinar(arq)
        d = json.loads(arq.read_text(encoding="utf-8"))
        d["tipo"] = "aceite"
        arq.write_bytes(decisoes.canonico(d))
        with mock.patch.dict(os.environ, {"PATH": str(falso) + os.pathsep + os.environ.get("PATH", "")}):
            self.assertNotEqual(Path(decisoes.ssh_keygen()).parent, falso)
            self.assertIn("não confere com o conteúdo", self.recusa(arq))



@unittest.skipUnless(os.name == "nt", "dono, direitos e ligações do Windows")
class TestSondagemDaAncora(unittest.TestCase):
    """Achado da sessão do preparo do host (2026-10-21): conferir só o arquivo e a pasta dele não basta. Quem apaga ou
    renomeia uma pasta acima (DELETE nela ou DELETE_CHILD na de cima), muda as permissões dela (WRITE_DAC, WRITE_OWNER)
    ou a troca por ligação põe outra âncora no mesmo caminho, e a sondagem diria "protegida". Os direitos vêm de um
    dublê (dar a uma pasta direitos que esta conta não tem exige administrador); a ligação é real (junção)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="decisoes-sonda-"))
        self.ancora = self.tmp / "FundacaoIA" / "confianca" / "allowed_signers"
        self.ancora.parent.mkdir(parents=True)
        self.ancora.write_text('titular namespaces="fundacao-decisao" ssh-ed25519 AAAA ensaio\n', encoding="ascii")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def sondar(self, concedidos: dict, ancora=None) -> dict:
        def direitos(caminho, pedidos):
            dados = concedidos.get(Path(caminho), set())
            return {nome: nome in dados for nome, _acesso in pedidos}
        with mock.patch.object(decisoes, "_sondas_de_escrita", return_value=(False, False)), \
                mock.patch.object(decisoes, "_direitos_windows", side_effect=direitos), \
                mock.patch.object(decisoes, "_dono_windows", return_value="Administradores"):
            return decisoes.conferir_ancora(ancora or self.ancora)

    def test_sem_direito_algum_no_caminho_a_ancora_e_protegida(self):
        r = self.sondar({})
        self.assertTrue(r["protegida"], r["motivo"])
        self.assertEqual([c["caminho"] for c in r["cadeia"]], [str(p) for p in (self.ancora, *self.ancora.parents)])

    def test_pasta_acima_que_deixa_renomear_a_pasta_da_ancora_e_acusada(self):
        base = self.ancora.parent.parent  # FundacaoIA: DELETE_CHILD nela renomeia confianca
        r = self.sondar({base: {"DELETE_CHILD"}})
        self.assertFalse(r["protegida"])
        self.assertIn("DELETE_CHILD em " + str(base), r["motivo"])

    def test_qualquer_pasta_acima_que_esta_conta_apaga_ou_muda_permissoes_e_acusada(self):
        for pasta in self.ancora.parents:
            for direito in ("WRITE_DAC", "WRITE_OWNER", "DELETE", "DELETE_CHILD"):
                with self.subTest(pasta=str(pasta), direito=direito):
                    self.assertFalse(self.sondar({pasta: {direito}})["protegida"])

    def test_pasta_da_ancora_que_pode_ser_renomeada_e_acusada(self):
        self.assertFalse(self.sondar({self.ancora.parent: {"DELETE"}})["protegida"])

    def test_ligacao_no_caminho_da_ancora_e_acusada(self):
        from apoio_auditoria import criar_ligacao_dir
        criar_ligacao_dir(self.tmp / "FundacaoIA-ligada", self.tmp / "FundacaoIA")
        r = self.sondar({}, ancora=self.tmp / "FundacaoIA-ligada" / "confianca" / "allowed_signers")
        self.assertFalse(r["protegida"])
        self.assertIn("ligação", r["motivo"])
        self.assertEqual([c["ligacao"] for c in r["cadeia"]][:3], [False, False, True])



if __name__ == "__main__":
    unittest.main()
