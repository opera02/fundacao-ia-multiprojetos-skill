"""1.7.11, lote L2 (desenho da jaula, §4.3 e §8): o `guarda_ferramentas.py` com a lista positiva de MCP por ferramenta.

Com FUNDACAO_MCP_FERRAMENTAS no ambiente (o perfil gerado a traz sempre, vazia sem a seção `mcp` da ficha), só passa a
ferramenta MCP cujo nome exato `mcp__<servidor>__<ferramenta>` está nela e cujo servidor está em FUNDACAO_MCP_PERMITIDAS.
Decisão do titular de 08/11/2026: ferramenta de gravação listada vale como a de consulta (o que decide é a ficha); a que
não está listada nega. Cada prova negativa abaixo falha no hook de antes (servidor inteiro) ou fecha o que a ficha não
listou: ferramenta fora da lista, outro servidor, sem a seção, lista malformada, curinga, nome ambíguo.
O guarda continua sem abrir arquivo, listar pasta nem criar processo (vigia de auditoria). Eventos fictícios; o nome do
servidor da conta (`claude_ai_...`) depende da medida M3 do desenho: aqui é só um nome de exemplo.
"""

from __future__ import annotations

import unittest

from test_hooks_1710 import FERRAMENTAS, carregar, decisao, ferramenta, motivo, rodar_vigiado

HOOK = "guarda_ferramentas.py"
SERVIDOR = "claude_ai_Conector_do_escritorio"
CONSULTA = ("buscar_clientes", "get_processo", "relatorio_prazos")
GRAVACAO = ("salvar_nota", "propor_operacoes", "confirmar_operacoes", "cancelar_operacoes",
            "atualizar_curadoria_precedente")
LISTA = ",".join(f"mcp__{SERVIDOR}__{f}" for f in (*CONSULTA, *GRAVACAO))
BASE = {"FUNDACAO_FERRAMENTAS": FERRAMENTAS, "FUNDACAO_MCP_PERMITIDAS": SERVIDOR, "FUNDACAO_MCP_FERRAMENTAS": LISTA}


def nome(f: str, servidor: str = SERVIDOR) -> str:
    return f"mcp__{servidor}__{f}"


class _Base(unittest.TestCase):
    def setUp(self):
        self.m = carregar(HOOK)

    def decide(self, ferramenta_mcp: str, **variaveis) -> str:
        env = {**BASE, **variaveis}
        env = {k: v for k, v in env.items() if v is not None}
        return "deny" if self.m.decide(ferramenta("x") | {"tool_name": ferramenta_mcp}, env) else "sem_decisao"

    def motivo(self, ferramenta_mcp: str, **variaveis) -> str:
        env = {k: v for k, v in {**BASE, **variaveis}.items() if v is not None}
        negativa = self.m.decide(ferramenta("x") | {"tool_name": ferramenta_mcp}, env)
        return negativa["hookSpecificOutput"]["permissionDecisionReason"] if negativa else ""


class ListaPositivaPorFerramenta(_Base):
    def test_ferramenta_listada_passa_consulta_e_gravacao(self):
        for f in (*CONSULTA, *GRAVACAO):
            with self.subTest(ferramenta=f):
                self.assertEqual(self.decide(nome(f)), "sem_decisao")

    def test_ferramenta_do_servidor_liberado_fora_da_lista_nega(self):
        """Prova negativa: servidor liberado não basta. Ferramenta nova ou renomeada fica negada até a ficha nova."""
        for f in ("get_cliente", "escanear_vault", "validar_frontmatter", "buscar_clientes_v2", "Buscar_clientes",
                  "buscar_clientes_", "excluir_nota", "apagar_tudo"):
            with self.subTest(ferramenta=f):
                self.assertEqual(self.decide(nome(f)), "deny")
        texto = self.motivo(nome("excluir_nota"))
        for trecho in ("'mcp__", "FUNDACAO_MCP_FERRAMENTAS", "ficha", "titular"):
            self.assertIn(trecho, texto)

    def test_gravacao_nao_listada_nega_mesmo_com_a_consulta_listada(self):
        so_consulta = ",".join(nome(f) for f in CONSULTA)
        for f in GRAVACAO:
            with self.subTest(ferramenta=f):
                self.assertEqual(self.decide(nome(f), FUNDACAO_MCP_FERRAMENTAS=so_consulta), "deny")
        for f in CONSULTA:
            self.assertEqual(self.decide(nome(f), FUNDACAO_MCP_FERRAMENTAS=so_consulta), "sem_decisao")

    def test_outro_servidor_nega_mesmo_com_o_nome_da_ferramenta_igual(self):
        for servidor in ("outro", "claude_ai_Outro", SERVIDOR + "x", "Claude_ai_Conector_do_escritorio", "fsn"):
            with self.subTest(servidor=servidor):
                self.assertEqual(self.decide(nome("buscar_clientes", servidor)), "deny")
                self.assertEqual(self.decide(nome("salvar_nota", servidor)), "deny")
        self.assertIn("'outro'", self.motivo(nome("buscar_clientes", "outro")))
        # servidor só na lista de ferramentas, fora de FUNDACAO_MCP_PERMITIDAS: continua negado
        self.assertEqual(self.decide(nome("x_y", "outro"), FUNDACAO_MCP_FERRAMENTAS=nome("x_y", "outro")), "deny")

    def test_sem_a_secao_nenhuma_mcp_passa(self):
        """O perfil gerado sem a seção traz as duas variáveis vazias: nenhuma ferramenta MCP, de nenhum servidor."""
        vazio = {"FUNDACAO_MCP_PERMITIDAS": "", "FUNDACAO_MCP_FERRAMENTAS": ""}
        for f in (*CONSULTA, *GRAVACAO):
            with self.subTest(ferramenta=f):
                self.assertEqual(self.decide(nome(f), **vazio), "deny")
                self.assertEqual(self.decide(nome(f), FUNDACAO_MCP_PERMITIDAS=None, FUNDACAO_MCP_FERRAMENTAS=None),
                                 "deny")
        # servidor liberado com a lista vazia, ou a lista sem o servidor liberado: também nada
        self.assertEqual(self.decide(nome("buscar_clientes"), FUNDACAO_MCP_FERRAMENTAS=""), "deny")
        self.assertEqual(self.decide(nome("buscar_clientes"), FUNDACAO_MCP_FERRAMENTAS=" , ,"), "deny")
        self.assertEqual(self.decide(nome("buscar_clientes"), FUNDACAO_MCP_PERMITIDAS=""), "deny")
        for outro in ("mcp__ccd_session__send_message", "mcp__plugin_x_y__z", "mcp__claude_ai_Gmail__send_message"):
            self.assertEqual(self.decide(outro), "deny", outro)

    def test_lista_malformada_nega_toda_mcp(self):
        mau = {"curinga": f"mcp__{SERVIDOR}__*", "padrão largo": "mcp__*", "só o servidor": SERVIDOR,
               "sem o prefixo": f"{SERVIDOR}__buscar_clientes", "ferramenta com dois separadores":
                   nome("buscar_clientes") + "," + nome("a__b"), "ferramenta com maiúscula": nome("Buscar"),
               "ferramenta vazia": f"mcp__{SERVIDOR}__", "separador triplo": f"mcp__{SERVIDOR}___buscar",
               "repetida": nome("buscar_clientes") + "," + nome("buscar_clientes"),
               "mais de 40": ",".join(nome(f"buscar_{i}") for i in range(41)),
               "grande demais": "x" * 9000, "com espaço no nome": f"mcp__{SERVIDOR}__buscar clientes"}
        for rotulo, lista in mau.items():
            with self.subTest(rotulo):
                for f in ("buscar_clientes", "get_processo"):
                    self.assertEqual(self.decide(nome(f), FUNDACAO_MCP_FERRAMENTAS=lista), "deny")
        self.assertIn("malformada", self.motivo(nome("buscar_clientes"), FUNDACAO_MCP_FERRAMENTAS="mcp__*"))
        # 40 nomes exatos ainda valem
        quarenta = ",".join(nome(f"buscar_{i}") for i in range(40))
        self.assertEqual(self.decide(nome("buscar_7"), FUNDACAO_MCP_FERRAMENTAS=quarenta), "sem_decisao")

    def test_nome_mcp_ambiguo_ou_malformado_continua_negado(self):
        for ruim in ("mcp__", f"mcp__{SERVIDOR}", f"mcp__{SERVIDOR}__", f"mcp__{SERVIDOR}__buscar__clientes",
                     f"mcp__{SERVIDOR}___buscar_clientes", f"mcp__{SERVIDOR}__buscar_clientes\n",
                     f"mcp__{SERVIDOR}__buscar_clientes ", f"mcp__{SERVIDOR}/x__buscar_clientes"):
            with self.subTest(ruim=ruim):
                self.assertEqual(self.decide(ruim, FUNDACAO_MCP_FERRAMENTAS=LISTA + "," + ruim), "deny")

    def test_variavel_ausente_e_o_comportamento_da_1710_e_o_perfil_gerado_nunca_a_deixa_ausente(self):
        """Sem FUNDACAO_MCP_FERRAMENTAS, vale o servidor inteiro, como na 1.7.10 (os testes de lá seguem). O preparo grava a
        variável sempre (vazia sem a seção) e `problemas_do_mcp_no_perfil` recusa o perfil sem ela."""
        self.assertEqual(self.decide(nome("excluir_nota"), FUNDACAO_MCP_FERRAMENTAS=None), "sem_decisao")
        self.assertEqual(self.decide(nome("excluir_nota"), FUNDACAO_MCP_FERRAMENTAS=None,
                                     FUNDACAO_MCP_PERMITIDAS=""), "deny")


class SubagentesEProcesso(_Base):
    def test_subagente_embutido_segue_a_mesma_lista(self):
        pasta = "/mnt/q/IA/fundacao/projects/juridico-lab"
        base = {"FUNDACAO_RAIZ": "/mnt/q/IA/fundacao", "FUNDACAO_PROJECT": "juridico-lab"}
        for f, esperado in (("buscar_clientes", "sem_decisao"), ("salvar_nota", "sem_decisao"), ("excluir_nota", "deny")):
            with self.subTest(ferramenta=f):
                e = ferramenta("x") | {"tool_name": nome(f), "agent_id": "ag-1", "agent_type": "general-purpose",
                                       "cwd": pasta}
                self.assertEqual("deny" if self.m.decide(e, {**BASE, **base}) else "sem_decisao", esperado)

    def test_agente_de_arquivo_nao_usa_mcp(self):
        pasta = "/mnt/q/IA/fundacao/projects/juridico-lab"
        e = ferramenta("x") | {"tool_name": nome("buscar_clientes"), "agent_id": "ag-1", "agent_type": "p:redator",
                               "cwd": pasta}
        env = {**BASE, "FUNDACAO_RAIZ": "/mnt/q/IA/fundacao", "FUNDACAO_PROJECT": "juridico-lab",
               "FUNDACAO_AGENTES": "p:redator=Read|Grep"}
        self.assertTrue(self.m.decide(e, env))

    def test_como_o_host_chama_e_sem_abrir_arquivo(self):
        for f, esperado in (("buscar_clientes", "sem_decisao"), ("salvar_nota", "sem_decisao"), ("excluir_nota", "deny")):
            with self.subTest(ferramenta=f):
                e = ferramenta(nome(f), termo="x")
                self.assertEqual(decisao(HOOK, e, **BASE), esperado)
                p = rodar_vigiado(HOOK, e, **BASE)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertTrue(p.stdout.isascii())
        self.assertEqual(decisao(HOOK, ferramenta(nome("salvar_nota")), FUNDACAO_FERRAMENTAS=FERRAMENTAS,
                                 FUNDACAO_MCP_PERMITIDAS="", FUNDACAO_MCP_FERRAMENTAS=""), "deny")
        self.assertIn("FUNDACAO_MCP_FERRAMENTAS", motivo(HOOK, ferramenta(nome("excluir_nota")), **BASE))

    def test_lista_de_ferramentas_da_sessao_ausente_nega_tudo_inclusive_mcp(self):
        env = {k: v for k, v in BASE.items() if k != "FUNDACAO_FERRAMENTAS"}
        self.assertEqual(self.m.decide(ferramenta(nome("buscar_clientes")), env)["hookSpecificOutput"]
                         ["permissionDecision"], "deny")


if __name__ == "__main__":
    unittest.main()
