"""Achado 4 da revisão independente do R179-37 (corrigido na 1.7.10): `KnowledgeService.search` não conferia o status
do projeto. Um projeto arquivado com permissão de leitura (o kit não arquiva: só por UPDATE direto no banco) ainda
respondia à busca, pela função, pela CLI (`conhecimento buscar`) e pelo servidor MCP (`buscar`), que usam a mesma
função.

Agora, depois da autorização, a busca recusa projeto inexistente ou inativo como `projects.project_root`:
`NotFound("projeto inexistente ou inativo", project_id=...)`, na mesma ordem (permissão negada antes, com o evento;
inativo depois) e sem conteúdo nem evento de recuperação. O projeto ativo continua respondendo. Raiz descartável com
projetos e identidades de ensaio; o arquivamento é UPDATE no banco do teste.

Da revisão independente do pacote (1.7.10): o filtro dos trechos lia a tabela acl direto e não via a concessão que a
política deriva sem linha no banco — a de `sessao-<p>` com a trava de projeto do PORTEIRO (contratos do lote 2, §4) —,
e `conhecimento buscar` pelo porteiro devolveria lista vazia em silêncio. Agora entram no SQL os recursos que a
política autoriza: a concessão derivada acha o trecho do projeto e não o de caso, e o caso continua exigindo a
concessão do caso."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

from helpers import CANARIOS, FoundationTestCase

from fundacao.core import auth
from fundacao.core.auth import Policy, Principal, resource_case, resource_project
from fundacao.core.contracts import AccessDenied, NotFound
from fundacao.core.knowledge import KnowledgeService
from fundacao.core.projects import project_root

IDENTIDADE = "FUNDACAO_" + "PRINCIPAL"
TEM_MCP = importlib.util.find_spec("mcp") is not None
APROVADO = {c: {"resultado": "aprovado", "evidencia": f"conferido contra a página ({c})"}
            for c in ("origem", "fidelidade", "vigencia", "acesso", "finalidade")}
TEXTO = "Aurora procedimento fictício de conferência da minuta " + CANARIOS["juridico-lab"]
SESSAO = "sessao-juridico-lab"  # identidade de sessão do contrato do lote 2, §4 (sem linha no banco)
TRAVA = getattr(auth, "ENV_TRAVA", None)  # FUNDACAO_PROJETO_TRAVADO, quando o PORTEIRO estiver integrado


class TestBuscaProjetoInativo(FoundationTestCase):
    def setUp(self):
        super().setUp()
        kj, kr = KnowledgeService(self.root, self.con, self.jur), KnowledgeService(self.root, self.con, self.revisor)
        self.write_data("juridico-lab", "fontes/guia.md", TEXTO)
        kj.register_source("juridico-lab", "juridico-lab/GUIA-AURORA", 1, "fontes/guia.md")
        h = kj.prepare("juridico-lab/GUIA-AURORA", 1, [TEXTO])
        kj.index("juridico-lab/GUIA-AURORA", 1)
        kr.curate("juridico-lab/GUIA-AURORA", 1, APROVADO, h, review_due="2026-11-18", purpose="laboratório")

    def arquivar(self, status: str = "archived") -> None:
        self.con.execute("UPDATE project SET status = ? WHERE project_id = 'juridico-lab'", (status,))

    def eventos(self, tipo: str, sujeito: str) -> int:
        return self.con.execute("SELECT COUNT(*) FROM event WHERE kind = ? AND subject = ?",
                                (tipo, sujeito)).fetchone()[0]

    def buscar(self, principal, projeto: str = "juridico-lab", consulta: str = "Aurora"):
        return KnowledgeService(self.root, self.con, principal).search(projeto, consulta)

    def cli(self, principal: str, *args: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k != IDENTIDADE}
        env.update({"PYTHONDONTWRITEBYTECODE": "1", IDENTIDADE: principal})
        return subprocess.run([sys.executable, "-m", "fundacao", "--raiz", str(self.root), *args], capture_output=True,
                              text=True, encoding="utf-8", cwd=str(self.root), env=env)

    def test_ativo_continua_respondendo(self):
        hits = self.buscar(self.jur)
        self.assertTrue(hits)
        self.assertTrue(all(h["citation"].startswith("juridico-lab/GUIA-AURORA@1") for h in hits))
        p = self.cli("operador-juridico", "conhecimento", "buscar", "--projeto", "juridico-lab", "--consulta", "Aurora")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(json.loads(p.stdout)["trechos"])

    def test_arquivado_com_leitura_recusa_pela_funcao(self):
        self.arquivar()
        recuperacoes = self.eventos("retrieval", "operador-juridico")
        for consulta in ("Aurora", ""):  # sem termos também: o status vem antes de olhar a consulta
            with self.subTest(consulta=consulta):
                with self.assertRaises(NotFound) as ctx:
                    self.buscar(self.jur, consulta=consulta)
                self.assertEqual(ctx.exception.as_dict(), {"error": {"code": "E_NOT_FOUND",
                                                                     "message": "projeto inexistente ou inativo",
                                                                     "project_id": "juridico-lab"}})
        self.assertEqual(self.eventos("retrieval", "operador-juridico"), recuperacoes)  # nada foi recuperado
        self.arquivar("creating")  # o outro status inativo do esquema
        with self.assertRaises(NotFound):
            self.buscar(self.jur)
        self.arquivar("active")  # reativado, volta a responder
        self.assertTrue(self.buscar(self.jur))

    def test_arquivado_com_leitura_recusa_pela_cli(self):
        self.arquivar()
        for args in (("--consulta", "Aurora"), ()):
            with self.subTest(args=args):
                p = self.cli("operador-juridico", "conhecimento", "buscar", "--projeto", "juridico-lab", *args)
                self.assertEqual(p.returncode, 2, p.stdout)
                self.assertEqual(p.stdout, "")
                erro = json.loads(p.stderr)["error"]
                self.assertEqual((erro["code"], erro["message"], erro["project_id"]),
                                 ("E_NOT_FOUND", "projeto inexistente ou inativo", "juridico-lab"))
                self.assertNotIn(CANARIOS["juridico-lab"], p.stderr)

    def test_ordem_igual_a_do_project_root(self):
        # Sem permissão, a negativa vem antes (com o evento), mesmo com o projeto arquivado; com permissão, o inativo.
        # A busca e o project_root dão o mesmo erro para cada identidade, e um projeto inexistente com permissão
        # (concessão para um projeto fora da tabela) também dá NotFound nos dois.
        self.arquivar()
        self.policy.grant(self.admin, "operador-juridico", resource_project("fantasma-lab"), "read")
        for principal, projeto, esperado in ((self.eng, "juridico-lab", AccessDenied),
                                             (self.jur, "juridico-lab", NotFound),
                                             (self.revisor, "juridico-lab", NotFound),
                                             (self.jur, "fantasma-lab", NotFound)):
            with self.subTest(principal=principal.principal_id, projeto=projeto):
                negativas = self.eventos("access_denied", principal.principal_id)
                with self.assertRaises(esperado) as pela_busca:
                    self.buscar(principal, projeto)
                with self.assertRaises(esperado) as pelo_root:
                    project_root(self.root, self.con, principal, projeto, action="read")
                self.assertEqual(pela_busca.exception.as_dict(), pelo_root.exception.as_dict())
                self.assertEqual(self.eventos("access_denied", principal.principal_id),
                                 negativas + (2 if esperado is AccessDenied else 0))

    def test_citacao_de_projeto_arquivado_nao_vale_nem_traz_o_corpo(self):
        # Reconferência do pacote: a conferência da citação também não olhava o status do projeto e devolvia o corpo
        # do trecho do projeto arquivado a quem tem leitura. Sem permissão, a resposta continua a de inexistente.
        servico = KnowledgeService(self.root, self.con, self.jur)
        trecho = self.buscar(self.jur)[0]["chunk_id"]
        self.assertTrue(servico.verify_citation(trecho)["valid"])
        self.arquivar()
        res = servico.verify_citation(trecho)
        self.assertEqual(res, {"chunk_id": trecho, "valid": False, "reason": "projeto inexistente ou inativo"})
        alheio = KnowledgeService(self.root, self.con, self.eng).verify_citation(trecho)
        self.assertEqual(alheio["reason"], "trecho inexistente ou sem acesso")
        self.arquivar("active")
        self.assertIn(CANARIOS["juridico-lab"], servico.verify_citation(trecho)["body"])

    def test_o_servidor_mcp_usa_a_mesma_busca(self):
        codigo = (self.root / "fundacao" / "mcp_servidor.py").read_text(encoding="utf-8")
        self.assertIn("KnowledgeService(raiz, con, me).search(projeto, consulta)", codigo)

    @unittest.skipUnless(TEM_MCP, "pacote mcp ausente")
    def test_mcp_buscar_recusa_o_arquivado_sem_conteudo(self):
        from mcp import Client

        from fundacao.mcp_servidor import criar_servidor

        def chamar():
            app = criar_servidor(self.root)

            async def roteiro():
                async with Client(app) as client:
                    return await client.call_tool("buscar", {"projeto": "juridico-lab", "consulta": "Aurora"})

            return asyncio.run(roteiro())

        with mock.patch.dict(os.environ, {IDENTIDADE: "operador-juridico"}):
            ativo = chamar()
            self.arquivar()
            arquivado = chamar()
        self.assertFalse(ativo.is_error)
        self.assertIn("GUIA-AURORA", " ".join(c.text for c in ativo.content))
        self.assertTrue(arquivado.is_error)
        texto = " ".join(c.text for c in arquivado.content)
        self.assertIn("projeto inexistente ou inativo", texto)
        self.assertNotIn(CANARIOS["juridico-lab"], texto)


class PoliticaComConcessaoDerivada(Policy):
    """Dá a SESSAO leitura, escrita e uso de project:juridico-lab sem linha de ACL, como a trava de projeto do PORTEIRO
    faz para `sessao-<p>`; o resto vem da tabela acl."""

    def allowed(self, subject, action, resource):
        if subject == SESSAO:
            return resource == resource_project("juridico-lab") and action in ("read", "write", "use")
        return super().allowed(subject, action, resource)


class TestBuscaPelaPolitica(FoundationTestCase):
    def setUp(self):
        super().setUp()
        kj, kr = KnowledgeService(self.root, self.con, self.jur), KnowledgeService(self.root, self.con, self.revisor)
        for sid, caso in (("juridico-lab/GUIA-PROJETO", None), ("juridico-lab/GUIA-CASO", "caso-fic-001")):
            rel = f"fontes/{sid.split('/')[1].lower()}.md"
            self.write_data("juridico-lab", rel, TEXTO)
            kj.register_source("juridico-lab", sid, 1, rel, case_id=caso)
            h = kj.prepare(sid, 1, [TEXTO])
            kj.index(sid, 1)
            kr.curate(sid, 1, APROVADO, h, review_due="2026-11-18", purpose="laboratório")

    def fontes(self, principal, politica=None) -> set:
        servico = KnowledgeService(self.root, self.con, principal)
        if politica is not None:
            servico.policy = politica
        return {h["citation"].split("@")[0] for h in servico.search("juridico-lab", "Aurora")}

    def test_concessao_derivada_sem_linha_de_acl_acha_o_projeto_e_nao_o_caso(self):
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM acl WHERE subject = ?", (SESSAO,)).fetchone()[0], 0)
        sessao = Principal(SESSAO, "trava-de-projeto")
        self.assertEqual(self.fontes(sessao, PoliticaComConcessaoDerivada(self.con)), {"juridico-lab/GUIA-PROJETO"})
        with self.assertRaises(AccessDenied):  # sem a concessão derivada, a mesma identidade é negada
            self.fontes(sessao)

    def test_o_caso_continua_exigindo_a_concessao_do_caso(self):
        self.policy.register_principal(self.admin, "leitor-projeto")
        self.policy.grant(self.admin, "leitor-projeto", resource_project("juridico-lab"), "read")
        self.assertEqual(self.fontes(Principal("leitor-projeto", "teste-simulado")), {"juridico-lab/GUIA-PROJETO"})
        self.assertEqual(self.fontes(self.jur), {"juridico-lab/GUIA-PROJETO", "juridico-lab/GUIA-CASO"})
        self.policy.revoke(self.admin, "operador-juridico", resource_case("juridico-lab", "caso-fic-001"), "read")
        self.assertEqual(self.fontes(self.jur), {"juridico-lab/GUIA-PROJETO"})  # a revogação vale na busca seguinte

    @unittest.skipUnless(TRAVA, "a trava de projeto do PORTEIRO ainda não está neste kit (vale depois da integração)")
    def test_sessao_com_a_trava_do_porteiro_acha_o_projeto_e_nao_o_caso(self):
        sessao = Principal(SESSAO, "trava-de-projeto")
        with mock.patch.dict(os.environ, {TRAVA: "juridico-lab"}):
            self.assertEqual(self.fontes(sessao), {"juridico-lab/GUIA-PROJETO"})
        with mock.patch.dict(os.environ, {TRAVA: "reversa-lab"}), self.assertRaises(AccessDenied):
            self.fontes(sessao)  # trava de outro projeto: tudo negado


if __name__ == "__main__":
    unittest.main()
