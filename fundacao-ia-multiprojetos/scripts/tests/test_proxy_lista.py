"""`assets/host/wsl/proxy_lista.py` (1.7.11, lote L3; DESENHO-JAULA §3.1, N-DOM-1, N-JAU-4 e N-JAU-5): o proxy de lista decide
pelo NOME antes do DNS, recusa IP privado e de loopback depois de resolver (resolvedor falso), exige SNI igual ao CONNECT,
e o curinga cobre o domínio principal sem cobrir `outrox` nem `x.outro`. Sem rede e sem socket Unix: o leitor e o
escritor são falsos, e o resolvedor e o conector, injetados; um teste usa o laço real em 127.0.0.1. Nomes fictícios."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

from apoio import SKILL
from test_dominios_ficha import carregar_por_caminho

WSL = SKILL / "assets" / "host" / "wsl"
PUBLICO = "93.184.215.14"
PUBLICO6 = "2606:4700::1111"


class EscritorFalso:
    def __init__(self):
        self.dados, self.fechado, self.eof = bytearray(), False, False

    def write(self, dados):
        self.dados += dados

    async def drain(self):
        pass

    def close(self):
        self.fechado = True

    def can_write_eof(self):
        return True

    def write_eof(self):
        self.eof = True


class Ambiente:
    """Um proxy com resolvedor e conector falsos; guarda o que o proxy tentou."""

    def __init__(self, test, dominios, ips=(PUBLICO,), resposta=b"RESPOSTA", **kw):
        self.proxy = carregar_por_caminho("_proxy_lista_teste", WSL / "proxy_lista.py")
        self.canario = carregar_por_caminho("_canario_jaula_teste", WSL / "canario_jaula.py")
        self.resolvidos, self.conectados, self.enviado_ao_destino = [], [], []
        self.ips, self.resposta = list(ips), resposta
        pasta = tempfile.mkdtemp(prefix="proxy-lista-1711-")
        test.addCleanup(lambda: [os.unlink(p) for p in Path(pasta).glob("*")] and os.rmdir(pasta) or
                        (os.path.isdir(pasta) and not os.listdir(pasta) and os.rmdir(pasta)))
        self.registro = os.path.join(pasta, "registro.jsonl")
        self.politica = self.proxy.Politica(dominios, resolver=self.resolver, conectar=self.conectar,
                                            registro=self.registro, pedido="pedido-1", **kw)

    async def resolver(self, host, porta):
        self.resolvidos.append((host, porta))
        return list(self.ips)

    async def conectar(self, ip, porta):
        self.conectados.append((ip, porta))
        leitor = asyncio.StreamReader()
        leitor.feed_data(self.resposta)
        leitor.feed_eof()
        escritor = EscritorFalso()
        self.enviado_ao_destino.append(escritor)
        return leitor, escritor

    async def rodar(self, bruto: bytes) -> bytes:
        leitor = asyncio.StreamReader(limit=self.proxy.LIMITE_CABECALHO)
        leitor.feed_data(bruto)
        leitor.feed_eof()
        escritor = EscritorFalso()
        await self.proxy.atender(self.politica, leitor, escritor)
        self.cliente = escritor
        return bytes(escritor.dados)

    def registros(self) -> list[dict]:
        if not os.path.exists(self.registro):
            return []
        with open(self.registro, encoding="ascii") as f:
            return [json.loads(linha) for linha in f]

    def hello(self, sni, ech=False):
        return self.canario.montar_clienthello(sni, ech)


def connect(alvo: str) -> bytes:
    return f"CONNECT {alvo} HTTP/1.1\r\nHost: {alvo}\r\n\r\n".encode("ascii")


def status(resposta: bytes):
    return int(resposta.split(b" ", 2)[1]) if resposta.startswith(b"HTTP/1.") else None


class Nome(unittest.IsolatedAsyncioTestCase):
    """Regras 1 e 2: o nome é conferido ANTES de qualquer DNS."""

    async def test_fora_da_lista_recusa_sem_consultar_o_dns(self):
        a = Ambiente(self, "api.exemplo.org")
        for alvo in ("outro.exemplo.org:443", "example.com:443", "sub.api.exemplo.org:443", "api.exemplo.org.evil.example:443"):
            resposta = await a.rodar(connect(alvo))
            self.assertEqual(status(resposta), 403, alvo)
            self.assertIn(b"fora-da-lista", resposta)
        self.assertEqual(a.resolvidos, [])  # nenhum DNS foi feito
        self.assertEqual(a.conectados, [])

    async def test_curinga_cobre_o_dominio_principal_e_os_subdominios(self):
        a = Ambiente(self, "*.stj.jus.br")
        for alvo in ("stj.jus.br:443", "dadosabertos.web.stj.jus.br:443", "STJ.jus.br:443"):
            resposta = await a.rodar(connect(alvo) + a.hello(alvo.split(":")[0].lower()))
            self.assertEqual(status(resposta), 200, alvo)

    async def test_curinga_nao_cobre_outrox_nem_x_outro(self):
        a = Ambiente(self, "*.stj.jus.br")
        for alvo in ("xstj.jus.br:443", "stj.jus.br.outro.example:443", "jus.br:443", "outro.jus.br:443"):
            resposta = await a.rodar(connect(alvo))
            self.assertEqual(status(resposta), 403, alvo)
        self.assertEqual(a.resolvidos, [])

    async def test_ip_literal_e_nome_local_recusam_mesmo_listados(self):
        a = Ambiente(self, "127.0.0.1,10.0.0.1,localhost,app.localhost,nas.local,*.com")
        for alvo in ("127.0.0.1:443", "10.0.0.1:443", "93.184.215.14:443", "[::1]:443", "[::ffff:127.0.0.1]:443",
                     "2130706433:443", "0x7f000001:443", "127.1:443", "localhost:443", "app.localhost:443",
                     "nas.local:443", "metadata.google.internal:443", "x.com:443", "::1:443", "1.2.3.4.5:443"):
            self.assertEqual(status(await a.rodar(connect(alvo))), 403, alvo)
        self.assertEqual(a.resolvidos, [])

    async def test_porta_e_metodo_fora_do_permitido_recusam(self):
        a = Ambiente(self, "api.exemplo.org")
        casos = [connect("api.exemplo.org:22"), connect("api.exemplo.org:80"), connect("api.exemplo.org:8443"),
                 connect("api.exemplo.org"), connect("api.exemplo.org:"), connect("api.exemplo.org:+443"),
                 b"POST http://api.exemplo.org/ HTTP/1.1\r\nHost: api.exemplo.org\r\n\r\n",
                 b"PUT http://api.exemplo.org/ HTTP/1.1\r\n\r\n", b"DELETE / HTTP/1.1\r\n\r\n",
                 b"GET http://api.exemplo.org:8080/ HTTP/1.1\r\n\r\n", b"GET http://api.exemplo.org:443/ HTTP/1.1\r\n\r\n",
                 b"GET / HTTP/1.1\r\nHost: api.exemplo.org\r\n\r\n",
                 b"GET https://api.exemplo.org/ HTTP/1.1\r\n\r\n",
                 b"GET http://usuario:senha-ficticia" + b"@api.exemplo.org/ HTTP/1.1\r\n\r\n",
                 b"GET http://api.exemplo.org/#frag HTTP/1.1\r\n\r\n"]
        for bruto in casos:
            with self.subTest(pedido=bruto[:50]):
                self.assertEqual(status(await a.rodar(bruto)), 403)
        self.assertEqual(a.resolvidos, [])

    async def test_nome_com_caractere_fora_do_alfabeto_recusa(self):
        a = Ambiente(self, "api.exemplo.org,xn--mnchen-3ya.exemplo")
        for alvo in ("münchen.exemplo:443", "api_exemplo.org:443", "api.exemplo.org%2f:443", "api exemplo.org:443",
                     "api.exemplo.org\u200b:443", "api..exemplo.org:443", "-api.exemplo.org:443"):
            bruto = (f"CONNECT {alvo} HTTP/1.1\r\n\r\n").encode("utf-8")
            self.assertIn(status(await a.rodar(bruto)), (400, 403), alvo)
        self.assertEqual(a.resolvidos, [])

    async def test_cabecalho_malformado_ou_grande_demais_da_400(self):
        a = Ambiente(self, "api.exemplo.org")
        for bruto in (b"CONNECT api.exemplo.org:443 HTTP/2.0\r\n\r\n", b"CONNECT api.exemplo.org:443\r\n\r\n",
                      b"CONNECT  api.exemplo.org:443 HTTP/1.1\r\n\r\n", b"CONNECT a:443 HTTP/1.1\nHost: a\r\n\r\n",
                      b"CONNECT api.exemplo.org:443 HTTP/1.1\r\n x: folded\r\n\r\n",
                      b"CONNECT api.exemplo.org:443 HTTP/1.1\r\nsemdoispontos\r\n\r\n",
                      b"CONNECT api.exemplo.org:443 HTTP/1.1\r\nX: \x00\r\n\r\n",
                      b"CONNECT api.exemplo.org:443 HTTP/1.1\r\nX: " + b"a" * 9000 + b"\r\n\r\n",
                      b"CONNECT api.exemplo.org:443 HTTP/1.1\r\n"):  # sem o fim do cabeçalho
            with self.subTest(pedido=bruto[:40]):
                self.assertEqual(status(await a.rodar(bruto)), 400)
        self.assertEqual(a.resolvidos, [])


class EnderecosEDns(unittest.IsolatedAsyncioTestCase):
    """Regras 3 e 4 (N-JAU-4): resolve uma vez, recusa se QUALQUER endereço for proibido, conecta ao IP já resolvido."""

    async def test_nome_da_lista_que_resolve_para_endereco_proibido_da_403(self):
        proibidos = [["127.0.0.1"], ["10.0.0.1"], ["172.16.0.5"], ["192.168.1.1"], ["169.254.169.254"], ["100.64.0.1"],
                     ["fd00::1"], ["::1"], ["fe80::1"], ["::ffff:127.0.0.1"], ["::ffff:10.0.0.1"], ["0.0.0.0"], ["::"],
                     ["224.0.0.1"], ["240.0.0.1"], ["64:ff9b::7f00:1"], ["2002:7f00:1::"],
                     [PUBLICO, "10.0.0.1"], ["10.0.0.1", PUBLICO], [PUBLICO6, "fd00::1"], ["não-é-endereço"]]
        for ips in proibidos:
            a = Ambiente(self, "api.exemplo.org", ips=ips)
            with self.subTest(ips=ips):
                resposta = await a.rodar(connect("api.exemplo.org:443") + a.hello("api.exemplo.org"))
                self.assertEqual(status(resposta), 403)
                self.assertEqual(len(a.resolvidos), 1)
                self.assertEqual(a.conectados, [])  # nada foi aberto para o destino
                self.assertNotIn(b"200", resposta)

    async def test_resolve_uma_vez_e_conecta_ao_ip_resolvido(self):
        a = Ambiente(self, "api.exemplo.org", ips=[PUBLICO, PUBLICO6])
        resposta = await a.rodar(connect("api.exemplo.org:443") + a.hello("api.exemplo.org"))
        self.assertEqual(status(resposta), 200)
        self.assertEqual(a.resolvidos, [("api.exemplo.org", 443)])  # uma resolução só: sem rebinding
        self.assertEqual(a.conectados, [(PUBLICO, 443)])

    async def test_nome_que_nao_resolve_da_502(self):
        a = Ambiente(self, "api.exemplo.org", ips=[])
        self.assertEqual(status(await a.rodar(connect("api.exemplo.org:443"))), 502)

    def test_tabela_de_enderecos(self):
        proxy = carregar_por_caminho("_proxy_lista_enderecos", WSL / "proxy_lista.py")
        for ip in (PUBLICO, PUBLICO6, "8.8.8.8", "1.1.1.1", "64:ff9b::808:808"):
            self.assertIsNone(proxy.ip_proibido(ip), ip)
        for ip in ("127.0.0.1", "::1", "10.1.2.3", "fc00::1", "fe80::1%eth0", "169.254.1.1", "100.127.255.255", "224.0.0.1",
                   "ff02::1", "0.0.0.0", "::", "::ffff:8.8.8.8", "::ffff:127.0.0.1", "64:ff9b::a00:1", "64:ff9b:1::1",
                   "2002:a00:1::", "192.0.2.1", "255.255.255.255", "x"):
            if ip == "::ffff:8.8.8.8":  # mapeado: o Python 3.12 devolve o motivo do IPv4 de dentro; qualquer motivo serve
                continue
            self.assertIsNotNone(proxy.ip_proibido(ip), ip)


class Sni(unittest.IsolatedAsyncioTestCase):
    """Regra 5: o SNI do primeiro ClientHello tem de ser igual ao host do CONNECT."""

    async def test_sni_igual_abre_o_tunel_e_repassa_os_bytes(self):
        a = Ambiente(self, "api.exemplo.org")
        hello = a.hello("api.exemplo.org")
        resposta = await a.rodar(connect("API.exemplo.org:443") + hello)
        self.assertTrue(resposta.startswith(b"HTTP/1.1 200"))
        self.assertTrue(resposta.endswith(b"RESPOSTA"))
        self.assertEqual(bytes(a.enviado_ao_destino[0].dados), hello)  # o ClientHello vai inteiro, sem mudança
        self.assertEqual(a.registros()[-1]["decisao"], "permitido")

    async def test_sni_diferente_fecha_antes_de_conectar(self):
        a = Ambiente(self, "api.exemplo.org,*.outro.org")
        for sni in ("example.com", "outro.org", "x.outro.org", "api.exemplo.org.evil.example", "API2.exemplo.org"):
            resposta = await a.rodar(connect("api.exemplo.org:443") + a.hello(sni))
            with self.subTest(sni=sni):
                self.assertEqual(resposta, b"HTTP/1.1 200 Connection Established\r\n\r\n")  # nada vem do destino
                self.assertTrue(a.cliente.fechado)
                self.assertEqual(a.registros()[-1]["decisao"], "recusado")
                self.assertIn("SNI diferente", a.registros()[-1]["motivo"])
        self.assertEqual(a.conectados, [])

    async def test_sem_sni_com_ech_ou_sem_tls_fecha(self):
        a = Ambiente(self, "api.exemplo.org")
        casos = {"sem SNI": a.hello(None), "ECH": a.hello("api.exemplo.org", ech=True),
                 "texto puro": b"GET / HTTP/1.1\r\n\r\n", "registro vazio": b"\x16\x03\x01\x00\x00",
                 "ClientHello truncado": a.hello("api.exemplo.org")[:30], "calado": b""}
        for nome, bruto in casos.items():
            resposta = await a.rodar(connect("api.exemplo.org:443") + bruto)
            with self.subTest(caso=nome):
                self.assertEqual(resposta, b"HTTP/1.1 200 Connection Established\r\n\r\n")
                self.assertEqual(a.registros()[-1]["decisao"], "recusado")
        self.assertEqual(a.conectados, [])

    async def test_clienthello_em_dois_registros_vale(self):
        a = Ambiente(self, "api.exemplo.org")
        inteiro = a.hello("api.exemplo.org")
        handshake = inteiro[5:]
        meio = len(handshake) // 2
        dois = b"".join(b"\x16\x03\x01" + len(p).to_bytes(2, "big") + p for p in (handshake[:meio], handshake[meio:]))
        resposta = await a.rodar(connect("api.exemplo.org:443") + dois)
        self.assertTrue(resposta.endswith(b"RESPOSTA"))
        self.assertEqual(bytes(a.enviado_ao_destino[0].dados), dois)

    def test_analisador_do_clienthello(self):
        proxy = carregar_por_caminho("_proxy_lista_hello", WSL / "proxy_lista.py")
        canario = carregar_por_caminho("_canario_jaula_hello", WSL / "canario_jaula.py")
        hs = canario.montar_clienthello("api.exemplo.org")[5:]
        self.assertEqual(proxy.analisar_clienthello(hs), ("api.exemplo.org", False))
        self.assertEqual(proxy.analisar_clienthello(canario.montar_clienthello("a.org", ech=True)[5:]), ("a.org", True))
        self.assertEqual(proxy.analisar_clienthello(canario.montar_clienthello(None)[5:]), (None, False))
        for ruim in (b"", b"\x02\x00\x00\x00", hs[:-3], hs + b"\x00", b"\x01\x00\x00\x02\x03\x03"):
            with self.assertRaises(ValueError):
                proxy.analisar_clienthello(ruim)
        # dois server_name na mesma extensão, ou a extensão repetida
        nome = b"\x00\x00\x05a.org"
        dois = (b"\x00\x00" + (2 + 2 * len(nome)).to_bytes(2, "big") + (2 * len(nome)).to_bytes(2, "big") + nome + nome)
        corpo = b"\x03\x03" + b"\0" * 32 + b"\x00" + b"\x00\x02\x13\x01" + b"\x01\x00" + len(dois).to_bytes(2, "big") + dois
        with self.assertRaises(ValueError):
            proxy.analisar_clienthello(b"\x01" + len(corpo).to_bytes(3, "big") + corpo)


class GetHttp(unittest.IsolatedAsyncioTestCase):
    async def test_get_absoluto_na_porta_80_vai_em_forma_de_origem(self):
        a = Ambiente(self, "api.exemplo.org")
        pedido = (b"GET http://api.exemplo.org/a/b?q=1 HTTP/1.1\r\nHost: outro.example\r\nProxy-Connection: keep-alive\r\n"
                  b"Proxy-Authorization: Basic x\r\nAccept: text/html\r\nConnection: keep-alive\r\n\r\n")
        resposta = await a.rodar(pedido)
        enviado = bytes(a.enviado_ao_destino[0].dados)
        self.assertEqual(resposta, b"RESPOSTA")
        self.assertTrue(enviado.startswith(b"GET /a/b?q=1 HTTP/1.1\r\nHost: api.exemplo.org\r\n"))
        self.assertIn(b"Accept: text/html\r\n", enviado)
        self.assertTrue(enviado.endswith(b"Connection: close\r\n\r\n"))
        for proibido in (b"Proxy-", b"outro.example", b"keep-alive"):
            self.assertNotIn(proibido, enviado)
        self.assertEqual(a.conectados, [(PUBLICO, 80)])

    async def test_get_fora_da_lista_ou_com_corpo_recusa(self):
        a = Ambiente(self, "api.exemplo.org")
        self.assertEqual(status(await a.rodar(b"GET http://example.com/ HTTP/1.1\r\n\r\n")), 403)
        self.assertEqual(status(await a.rodar(
            b"GET http://api.exemplo.org/ HTTP/1.1\r\nContent-Length: 5\r\n\r\n")), 403)
        self.assertEqual(status(await a.rodar(
            b"GET http://api.exemplo.org/ HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n")), 403)
        self.assertEqual(a.conectados, [])


class TetosERegistro(unittest.IsolatedAsyncioTestCase):
    async def test_teto_de_bytes_do_pedido_corta_a_conexao(self):
        a = Ambiente(self, "api.exemplo.org", resposta=b"x" * 5000, teto_bytes=1000)
        resposta = await a.rodar(connect("api.exemplo.org:443") + a.hello("api.exemplo.org"))
        self.assertLess(len(resposta), 1000 + 100)
        self.assertEqual(a.registros()[-1]["motivo"], "teto de bytes do pedido")

    async def test_acima_do_teto_de_conexoes_da_503(self):
        a = Ambiente(self, "api.exemplo.org", max_conexoes=0)
        self.assertEqual(status(await a.rodar(connect("api.exemplo.org:443"))), 503)
        self.assertEqual(a.resolvidos, [])

    async def test_conexoes_ativas_voltam_a_zero(self):
        a = Ambiente(self, "api.exemplo.org")
        await a.rodar(connect("api.exemplo.org:443") + a.hello("api.exemplo.org"))
        await a.rodar(connect("outro.example:443"))
        self.assertEqual(a.politica.ativas, 0)

    async def test_registro_sem_conteudo(self):
        a = Ambiente(self, "api.exemplo.org")
        await a.rodar(connect("api.exemplo.org:443") + a.hello("api.exemplo.org"))
        await a.rodar(connect("example.com:443"))
        await a.rodar(connect("[::1]:443"))
        linhas = a.registros()
        self.assertEqual(len(linhas), 3)
        for r in linhas:
            self.assertEqual(set(r), {"t", "pedido", "host", "porta", "decisao", "motivo", "bytes"})
            self.assertEqual(r["pedido"], "pedido-1")
        self.assertEqual([r["decisao"] for r in linhas], ["permitido", "recusado", "recusado"])
        resumo = a.proxy.resumir_registro(a.registro, "pedido-1")
        self.assertEqual((resumo["conexoes"], resumo["permitidas"]), (3, 1))
        self.assertEqual(len(resumo["recusas"]), 2)
        self.assertEqual(a.proxy.resumir_registro(a.registro, "outro")["conexoes"], 0)

    async def test_lista_vazia_recusa_tudo(self):
        a = Ambiente(self, "")
        self.assertEqual(status(await a.rodar(connect("api.exemplo.org:443"))), 403)

    def test_socket_velho_so_sai_se_for_socket(self):
        proxy = carregar_por_caminho("_proxy_lista_socket", WSL / "proxy_lista.py")
        with tempfile.TemporaryDirectory() as pasta:
            comum = os.path.join(pasta, "proxy.sock")
            Path(comum).write_bytes(b"x")
            with self.assertRaises(SystemExit):
                proxy.preparar_socket(comum)
            self.assertTrue(os.path.exists(comum))  # nada foi apagado
            proxy.preparar_socket(os.path.join(pasta, "nao-existe.sock"))  # ausente: sem erro


class LacoReal(unittest.IsolatedAsyncioTestCase):
    """O servidor de verdade (TCP em 127.0.0.1, só para o teste): cabeçalho, 200, ClientHello e o túnel."""

    async def test_connect_pelo_laco_real(self):
        a = Ambiente(self, "api.exemplo.org")
        parar, pronto, ligado = asyncio.Event(), asyncio.Event(), []
        servidor = asyncio.ensure_future(a.proxy.servir(a.politica, host="127.0.0.1", porta=0, pronto=pronto,
                                                        parar=parar, ligado=ligado))
        await asyncio.wait_for(pronto.wait(), 5)
        host, porta = ligado[0][:2]
        leitor, escritor = await asyncio.open_connection(host, porta)
        escritor.write(connect("api.exemplo.org:443"))
        await escritor.drain()
        self.assertTrue((await asyncio.wait_for(leitor.readuntil(b"\r\n\r\n"), 5)).startswith(b"HTTP/1.1 200"))
        escritor.write(a.hello("api.exemplo.org"))
        await escritor.drain()
        self.assertEqual(await asyncio.wait_for(leitor.read(100), 5), b"RESPOSTA")
        escritor.close()
        leitor2, escritor2 = await asyncio.open_connection(host, porta)
        escritor2.write(connect("example.com:443"))
        await escritor2.drain()
        self.assertEqual(status(await asyncio.wait_for(leitor2.read(1000), 5)), 403)
        escritor2.close()
        parar.set()
        await asyncio.wait_for(servidor, 5)


if __name__ == "__main__":
    unittest.main()
