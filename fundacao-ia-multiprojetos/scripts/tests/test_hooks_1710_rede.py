"""`assets/hooks/guarda_rede.py` (contratos do lote 2 da 1.7.10, §2 e §7): WebFetch só para domínio de
FUNDACAO_DOMINIOS_WEB (exato ou `*.d` casando subdomínio, nunca o próprio `d` por `*.d`), sem IP, sem porta estranha,
só http/https, URL malformada nega; WebSearch só com FUNDACAO_WEBSEARCH=1; a decisão é `deny`, nunca pergunta.

URLs fictícias; as que têm usuário na autoridade são montadas em tempo de execução (a varredura de segredos da
liberação acusa texto com cara de endereço de e-mail).
"""

from __future__ import annotations

import unittest

from test_hooks_1710 import carregar, decisao, ferramenta, motivo

HOOK = "guarda_rede.py"
ARROBA = "@"


class GuardaRede(unittest.TestCase):
    def setUp(self):
        self.m = carregar(HOOK)

    def decide(self, url, lista="docs.exemplo.com.br,*.api.exemplo.org", **env):
        env = {"FUNDACAO_DOMINIOS_WEB": lista, **env} if lista is not None else env
        return "deny" if self.m.decide({"tool_name": "WebFetch", "tool_input": {"url": url, "prompt": "x"}},
                                       env) else "sem_decisao"

    def test_dominio_exato_da_lista_segue(self):
        for url in ("https://docs.exemplo.com.br/guia", "http://docs.exemplo.com.br/", "https://DOCS.Exemplo.COM.br/a",
                    "https://docs.exemplo.com.br./x", "https://docs.exemplo.com.br:443/x",
                    "http://docs.exemplo.com.br:80/x", "https://docs.exemplo.com.br?q=1#frag"):
            with self.subTest(url=url):
                self.assertEqual(self.decide(url), "sem_decisao")
        self.assertEqual(decisao(HOOK, ferramenta("WebFetch", url="https://docs.exemplo.com.br/a", prompt="x"),
                                 FUNDACAO_DOMINIOS_WEB="docs.exemplo.com.br"), "sem_decisao")

    def test_curinga_casa_subdominio_e_nunca_o_proprio_dominio(self):
        self.assertEqual(self.decide("https://v1.api.exemplo.org/x"), "sem_decisao")
        self.assertEqual(self.decide("https://a.b.api.exemplo.org/x"), "sem_decisao")
        self.assertEqual(self.decide("https://api.exemplo.org/x"), "deny")
        self.assertEqual(self.decide("https://api.exemplo.org/x", lista="*.api.exemplo.org,api.exemplo.org"),
                         "sem_decisao")
        for url in ("https://exemplo.org/", "https://xapi.exemplo.org/", "https://api.exemplo.org.evil.example/",
                    "https://subdocs.exemplo.com.br/", "https://docs.exemplo.com.br.evil.example/",
                    "https://evil.example/docs.exemplo.com.br"):
            with self.subTest(url=url):
                self.assertEqual(self.decide(url), "deny")

    def test_ip_literal_nega_mesmo_listado(self):
        lista = "127.0.0.1,10.0.0.1,2130706433,0x7f000001,127.1,[::1],::1,169.254.169.254"
        for url in ("http://127.0.0.1/", "http://10.0.0.1/", "http://2130706433/", "http://0x7f000001/",
                    "http://127.1/", "http://0177.0.0.1/", "http://[::1]/", "http://[::ffff:127.0.0.1]/",
                    "http://169.254.169.254/latest/meta-data/", "http://1.2.3.4.5/"):
            with self.subTest(url=url):
                self.assertEqual(self.decide(url, lista=lista), "deny")
        self.assertIn("IP literal", motivo(HOOK, ferramenta("WebFetch", url="http://127.0.0.1/"),
                                          FUNDACAO_DOMINIOS_WEB="127.0.0.1"))

    def test_nome_local_nega_mesmo_listado(self):
        lista = "localhost,app.localhost,nas.local,svc.internal"
        for url in ("http://localhost/", "http://LOCALHOST./", "http://app.localhost/", "http://nas.local/",
                    "http://svc.internal/"):
            with self.subTest(url=url):
                self.assertEqual(self.decide(url, lista=lista), "deny")

    def test_porta_fora_da_padrao_nega(self):
        for url in ("https://docs.exemplo.com.br:8443/", "http://docs.exemplo.com.br:443/",
                    "https://docs.exemplo.com.br:80/", "https://docs.exemplo.com.br:99999/",
                    "https://docs.exemplo.com.br:+443/", "https://docs.exemplo.com.br:x/"):
            with self.subTest(url=url):
                self.assertEqual(self.decide(url), "deny")

    def test_esquema_que_nao_e_http_nega(self):
        for url in ("file:///etc/passwd", "file://docs.exemplo.com.br/x", "ftp://docs.exemplo.com.br/x",
                    "javascript:alert(1)", "data:text/plain,oi", "https:/docs.exemplo.com.br/x",
                    "https:docs.exemplo.com.br/x", "//docs.exemplo.com.br/x", "docs.exemplo.com.br/x",
                    "gopher://docs.exemplo.com.br/", "ws://docs.exemplo.com.br/"):
            with self.subTest(url=url):
                self.assertEqual(self.decide(url), "deny")

    def test_usuario_na_url_e_truques_de_autoridade_negam(self):
        urls = ["https://usuario" + ARROBA + "docs.exemplo.com.br/",
                "https://usuario:senha-ficticia" + ARROBA + "docs.exemplo.com.br/",
                "https://docs.exemplo.com.br" + ARROBA + "evil.example/",
                "https://evil.example\\" + ARROBA + "docs.exemplo.com.br/",
                "https://docs.exemplo.com.br\\.evil.example/",
                "https://evil.example\t" + ARROBA + "docs.exemplo.com.br/",
                "https://docs.exemplo.com.br\n.evil.example/", " https://docs.exemplo.com.br/",
                "https://docs.exemplo.com.br /", "https://docs\u200b.exemplo.com.br/",
                "https://%64ocs.exemplo.com.br/", "https://docs.exemplo.com.br%2f.evil.example/",
                "https://docs..exemplo.com.br/", "https://-docs.exemplo.com.br/", "https://docs_x.exemplo.com.br/",
                "https:///docs.exemplo.com.br/", "https://", "", "h" * 9000]
        for url in urls:
            with self.subTest(url=url[:60]):
                self.assertEqual(self.decide(url), "deny")

    def test_nome_internacional_compara_em_ascii(self):
        lista = "xn--mnchen-3ya.exemplo"
        self.assertEqual(self.decide("https://münchen.exemplo/", lista=lista), "sem_decisao")
        self.assertEqual(self.decide("https://xn--mnchen-3ya.exemplo/", lista="münchen.exemplo"), "sem_decisao")
        self.assertEqual(self.decide("https://münchen.exemplo/", lista="munchen.exemplo"), "deny")
        # ponto ideográfico vira ponto, como no navegador: só vale se o nome resultante estiver na lista
        self.assertEqual(self.decide("https://evil。example/", lista="docs.exemplo.com.br"), "deny")

    def test_lista_ausente_ou_vazia_nega_todo_webfetch(self):
        for lista in (None, "", " ", ",,"):
            with self.subTest(lista=lista):
                self.assertEqual(self.decide("https://docs.exemplo.com.br/", lista=lista), "deny")
        texto = motivo(HOOK, ferramenta("WebFetch", url="https://docs.exemplo.com.br/x"))
        for trecho in ("docs.exemplo.com.br", "FUNDACAO_DOMINIOS_WEB", "ficha de aberturas", "titular"):
            self.assertIn(trecho, texto)

    def test_entrada_invalida_da_lista_nao_libera_nada(self):
        for lista in ("*.com", "*", "*.*", "*example.com", "exemplo.*", "docs.exemplo.com.br:443",
                      "https://docs.exemplo.com.br", "docs.exemplo.com.br/x", "docs exemplo.com.br",
                      "*.*.exemplo.com.br", "docs.exemplo.com.br.."):
            with self.subTest(lista=lista):
                self.assertEqual(self.decide("https://docs.exemplo.com.br/", lista=lista), "deny")
                self.assertEqual(self.decide("https://x.docs.exemplo.com.br/", lista=lista), "deny")

    def test_websearch_so_com_a_abertura(self):
        evento = ferramenta("WebSearch", query="jurisprudencia ficticia")
        self.assertEqual(decisao(HOOK, evento, FUNDACAO_WEBSEARCH="1"), "sem_decisao")
        for valor in (None, "", "0", "true", "sim", " 1", "1 "):
            env = {} if valor is None else {"FUNDACAO_WEBSEARCH": valor}
            with self.subTest(valor=valor):
                self.assertEqual("deny" if self.m.decide(evento, env) else "sem_decisao", "deny")
        self.assertIn("ficha de aberturas", motivo(HOOK, evento))

    def test_webfetch_sem_url_ou_com_entrada_ruim_nega(self):
        for entrada in ({}, {"url": None}, {"url": 7}, {"url": ["https://docs.exemplo.com.br/"]}):
            with self.subTest(entrada=entrada):
                self.assertEqual(decisao(HOOK, {"tool_name": "WebFetch", "tool_input": entrada},
                                         FUNDACAO_DOMINIOS_WEB="docs.exemplo.com.br"), "deny")
        self.assertEqual(decisao(HOOK, {"tool_name": "WebFetch", "tool_input": "https://docs.exemplo.com.br/"},
                                 FUNDACAO_DOMINIOS_WEB="docs.exemplo.com.br"), "deny")

    def test_outras_ferramentas_sem_decisao(self):
        for nome in ("Read", "Bash", "mcp__fundacao__status"):
            with self.subTest(nome=nome):
                self.assertEqual(decisao(HOOK, ferramenta(nome, url="https://evil.example/")), "sem_decisao")


if __name__ == "__main__":
    unittest.main()
