"""`assets/host/wsl/dominios_ficha.py` (1.7.11, lote L3; DESENHO-JAULA §3.1 regra 2, N-DOM-1 e N-JAU-5): a cópia da regra de
domínios que a jaula carrega decide IGUAL ao `guarda_rede.py` (hook), ao `aberturas_regras.cobre` (kit) e ao que o proxy
de lista aplica, numa tabela comum. DECISAO-010, item 5: `*.x` cobre `x` e os subdomínios; nunca `outrox` nem `x.outro`.
Domínios fictícios."""

from __future__ import annotations

import importlib.util
import sys
import unittest

from apoio import KIT, SKILL
from test_hooks_1710 import carregar as carregar_hook

WSL = SKILL / "assets" / "host" / "wsl"


def carregar_por_caminho(nome: str, caminho):
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(nome, caminho)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nome] = modulo
    spec.loader.exec_module(modulo)
    return modulo


# (lista da ficha, host como vem da URL/CONNECT, deve cobrir?)
TABELA = [
    ("*.stj.jus.br", "stj.jus.br", True),                      # N-DOM-1: o domínio principal
    ("*.stj.jus.br", "dadosabertos.web.stj.jus.br", True),     # e qualquer subdomínio
    ("*.stj.jus.br", "web.stj.jus.br", True),
    ("*.stj.jus.br", "xstj.jus.br", False),                    # nunca outrox
    ("*.stj.jus.br", "stj.jus.br.outro.example", False),       # nem x.outro
    ("*.stj.jus.br", "jus.br", False),                         # nem o pai
    ("*.stj.jus.br", "outro.jus.br", False),                   # nem um irmão
    ("stj.jus.br", "stj.jus.br", True),
    ("stj.jus.br", "www.stj.jus.br", False),                   # exato não cobre filho
    ("*.api.exemplo.org,docs.exemplo.com.br", "API.Exemplo.ORG", True),    # caixa
    ("*.api.exemplo.org,docs.exemplo.com.br", "api.exemplo.org.", True),   # ponto final
    ("*.api.exemplo.org,docs.exemplo.com.br", "v1.api.exemplo.org", True),
    ("*.api.exemplo.org,docs.exemplo.com.br", "docs.exemplo.com.br", True),
    ("*.api.exemplo.org,docs.exemplo.com.br", "x.docs.exemplo.com.br", False),
    ("*.api.exemplo.org,docs.exemplo.com.br", "exemplo.org", False),
    ("*.com", "x.com", False),                                 # um rótulo só não vale como curinga
    ("*.com", "com", False),
    ("*", "x.com", False),
    ("127.0.0.1", "127.0.0.1", False),                         # IP literal nunca, nem listado
    ("2130706433,0x7f000001", "2130706433", False),
    ("localhost,app.localhost,nas.local,svc.internal", "localhost", False),
    ("localhost,app.localhost,nas.local,svc.internal", "app.localhost", False),
    ("localhost,app.localhost,nas.local,svc.internal", "svc.internal", False),
    ("*.x.local", "a.x.local", False),
    ("docs.exemplo.com.br", "docs.exemplo.com.br.evil.example", False),
    ("docs.exemplo.com.br", "docs-exemplo.com.br", False),
    ("docs.exemplo.com.br", "docs..exemplo.com.br", False),
    ("docs.exemplo.com.br", "-docs.exemplo.com.br", False),
    ("docs.exemplo.com.br", "docs_x.exemplo.com.br", False),
    ("xn--mnchen-3ya.exemplo", "münchen.exemplo", True),       # internacional compara em ASCII
    ("münchen.exemplo", "xn--mnchen-3ya.exemplo", True),
    ("munchen.exemplo", "münchen.exemplo", False),
    ("strasse.exemplo", "straße.exemplo", False),              # ß não vira ss
    ("", "x.com", False),                                      # lista vazia nega tudo
]


class DominiosFicha(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dom = carregar_por_caminho("_dominios_ficha_teste", WSL / "dominios_ficha.py")
        cls.hook = carregar_hook("guarda_rede.py")
        cls.regras = carregar_por_caminho("_regras_kit_dominios_ficha", KIT / "fundacao" / "core" / "aberturas_regras.py")

    def hook_cobre(self, lista: str, host: str) -> bool:
        """O que o hook decide para `https://<host>/`; URL que o hook nem aceita como URL conta como não coberta."""
        host_url = host if ":" not in host else f"[{host}]"
        evento = {"tool_name": "WebFetch", "tool_input": {"url": f"https://{host_url}/", "prompt": "x"}}
        return self.hook.decide(evento, {"FUNDACAO_DOMINIOS_WEB": lista}) is None

    def test_a_copia_decide_como_o_hook_na_tabela_comum(self):
        for lista, host, esperado in TABELA:
            with self.subTest(lista=lista, host=host):
                self.assertEqual(self.dom.casa(host, lista), esperado)
                self.assertEqual(self.hook_cobre(lista, host), esperado)

    def test_a_copia_decide_como_o_cobre_do_kit(self):
        """O `cobre` do kit e o da jaula: entrada a entrada, sobre o host já normalizado."""
        for lista, host, _ in TABELA:
            host_n = self.dom.host_normalizado(host)
            if host_n is None or self.dom.proibido_sempre(host_n):
                continue
            for entrada in [e.strip() for e in lista.split(",") if e.strip()]:
                with self.subTest(entrada=entrada, host=host_n):
                    self.assertEqual(self.dom.cobre(entrada, host_n), self.regras.cobre(entrada, host_n))

    def test_o_curinga_cobre_o_principal_e_o_perfil_expandido_decide_igual(self):
        """N-DOM-1: o perfil gera `x` e `*.x`; a lista expandida decide como a da ficha."""
        for lista, host, _ in TABELA:
            entradas = [e.strip() for e in lista.split(",") if e.strip()]
            if any(e.startswith("*.") and "." not in e[2:] for e in entradas) or "*" in entradas:
                continue  # `*.com` nunca chega ao perfil: o validador da ficha o recusa antes
            expandida = self.dom.expandir_curingas(entradas)
            with self.subTest(lista=lista, host=host):
                self.assertEqual(self.dom.casa(host, expandida), self.dom.casa(host, entradas))
                self.assertEqual(expandida, self.dom.expandir_curingas(expandida))  # idempotente
                self.assertEqual(expandida, self.regras.expandir_curingas(entradas))  # e é a regra do kit
        self.assertEqual(self.dom.expandir_curingas(["*.x.com", "y.com"]), ["x.com", "*.x.com", "y.com"])

    def test_o_proxy_decide_como_a_copia(self):
        """N-JAU-5: o proxy de lista e `dominios_ficha.casa` decidem igual para o nome do CONNECT (ASCII)."""
        proxy = carregar_por_caminho("_proxy_lista_dominios_ficha", WSL / "proxy_lista.py")
        for lista, host, esperado in TABELA:
            if not host.isascii() or host.endswith("."):
                continue  # o proxy é mais estrito: só [A-Za-z0-9.-] e sem ponto final (regra 1)
            politica = proxy.Politica(lista)
            with self.subTest(lista=lista, host=host):
                try:
                    proxy.conferir_nome(politica, True, host, 443)
                    decidiu = True
                except proxy.Recusa:
                    decidiu = False
                self.assertEqual(decidiu, esperado)

    def test_entrada_invalida_da_lista_nao_libera_nada(self):
        for lista in ("https://x.com", "x.com:443", "x.com/a", "*.x.*.com", "x*.com", "usuario" + "@" + "x.com", " ", ","):
            with self.subTest(lista=lista):
                self.assertFalse(self.dom.casa("x.com", lista))
                self.assertEqual(self.dom.lista_de_dominios(lista), (set(), set()))

    def test_exemplo_concreto_para_o_canario(self):
        self.assertEqual(self.dom.exemplo_concreto(["*.stj.jus.br"]), "stj.jus.br")
        self.assertEqual(self.dom.exemplo_concreto(["*.a.org", "b.org"]), "b.org")
        self.assertIsNone(self.dom.exemplo_concreto(["127.0.0.1", "*.com"]))

    def test_texto_com_virgulas_e_sequencia_dao_o_mesmo(self):
        self.assertEqual(self.dom.lista_de_dominios("a.com, *.b.com"), self.dom.lista_de_dominios(["a.com", "*.b.com"]))


if __name__ == "__main__":
    unittest.main()
