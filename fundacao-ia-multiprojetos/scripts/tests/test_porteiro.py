"""Porteiro da sessão de projeto (assets/host/wsl/porteiro.py, 1.7.10; contratos do lote 2, §4), nas partes que não
dependem do Linux: porteiro.json no esquema fechado, hash da árvore do kit, pedido tipado (mapa fixo, sem abreviação,
sem --raiz nem --ancora, só o projeto da configuração, caminho só dentro de projects/<p>/), formato do pedido e da
resposta, ambiente mínimo e o mapa igual ao do kit (crítica do desenho: "testar a lista do porteiro contra o parser
do kit"). Da revisão do lote 2: texto fora do UTF-8 e criado_em fora do ISO UTC recusados, nome fora do UTF-8 no kit
sem traceback, a cópia privada conferida do kit, a renovação da trava que falha sem deixar temporário e o pid do
lançador inválido. Da correção do lote 2: a idade máxima do pedido (a soma com o prazo do kit cabe no corte de 120 s do
Bash), o teto do kit conferido por fluxo (nada além dele vai para a cópia), o pid acima do pid_t e `eventos` e `memoria
licao historico` fora do mapa (emenda E2). Da reconferência 3: a limpeza das pastas de trabalho na partida, com um
/proc de ensaio (a pasta em uso fica; com /proc ilegível, nenhuma sai). Da integração (item I3): a `abertura` com as
opções de cada ação, sem --arquivo, conferida nos subparsers do kit. Rodam no Windows e no Linux; a fila por
descritor, o aperto de mão e a execução ficam em test_porteiro_fila.py e test_porteiro_kit.py, só no Linux. Pastas
descartáveis e dados fictícios."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from apoio import ENV, KIT, SKILL, criar_ligacao_dir

PORTEIRO = SKILL / "assets" / "host" / "wsl" / "porteiro.py"
if str(KIT) not in sys.path:
    sys.path.insert(0, str(KIT))
from fundacao import porteiro_cliente  # noqa: E402
from fundacao.__main__ import build_parser  # noqa: E402
from fundacao.core.auth import COMANDOS_DA_TRAVA  # noqa: E402


def carregar():
    spec = importlib.util.spec_from_file_location("porteiro_teste", PORTEIRO)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def kit_ficticio(raiz: Path, versao: str = "1.7.10", principal: str = "def main(argv):\n    return 0\n") -> None:
    (raiz / "fundacao" / "core").mkdir(parents=True, exist_ok=True)
    (raiz / "fundacao" / "__init__.py").write_text(f'KIT_VERSION = "{versao}"\n', encoding="utf-8")
    (raiz / "fundacao" / "__main__.py").write_text(principal, encoding="utf-8")
    (raiz / "fundacao" / "core" / "__init__.py").write_text("", encoding="utf-8")


class PorteiroCase(unittest.TestCase):
    def setUp(self):
        self.mod = carregar()
        self.base = Path(tempfile.mkdtemp(prefix="porteiro-1710-"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.raiz = self.base / "raiz"
        kit_ficticio(self.raiz)
        for projeto in ("proj-a", "proj-b"):
            (self.raiz / "projects" / projeto / "decisoes").mkdir(parents=True)
        self.proj = self.raiz / "projects" / "proj-a"

    def config(self, **mudar) -> dict:
        return {"schema_version": "fundacao.porteiro/1", "raiz": str(self.raiz), "projeto": "proj-a",
                "kit_sha256": self.mod.sha256_do_kit(self.raiz), "assinante": "titular-ficticio",
                "operacoes": {"fundacao": {}}, **mudar}

    def gravar(self, conteudo, nome: str = "porteiro.json") -> Path:
        arq = self.base / "etc" / nome
        arq.parent.mkdir(exist_ok=True)
        arq.write_bytes(conteudo if isinstance(conteudo, bytes) else json.dumps(conteudo).encode("utf-8"))
        return arq


class TestConfiguracao(PorteiroCase):
    def test_configuracao_valida_e_o_hash_do_arquivo(self):
        arq = self.gravar(self.config())
        cfg, sha = self.mod.carregar_config(arq)
        self.assertEqual(cfg["projeto"], "proj-a")
        self.assertEqual(sha, hashlib.sha256(arq.read_bytes()).hexdigest())

    def test_cada_desvio_do_esquema_e_recusado(self):
        sem_assinante = self.config()
        del sem_assinante["assinante"]
        casos = {"campo a mais": (self.config(extra="x"), "esquema"), "campo a menos": (sem_assinante, "esquema"),
                 "schema": (self.config(schema_version="fundacao.porteiro/2"), "schema_version"),
                 "raiz relativa": (self.config(raiz="raiz-relativa"), "absoluto"),
                 "projeto maiúsculo": (self.config(projeto="Proj-A"), "identificador"),
                 "projeto com --": (self.config(projeto="proj--a"), "identificador"),
                 "projeto reservado": (self.config(projeto="con"), "identificador"),
                 "sha curto": (self.config(kit_sha256="a" * 63), "SHA-256"),
                 "sha maiúsculo": (self.config(kit_sha256="A" * 64), "SHA-256"),
                 "assinante de sessão": (self.config(assinante="sessao-proj-a"), "titular"),
                 "assinante com espaço": (self.config(assinante="titular ficticio"), "titular"),
                 "sem operações": (self.config(operacoes={}), "fundacao"),
                 "fundação com parâmetro": (self.config(operacoes={"fundacao": {"prazo": 5}}), "exatamente"),
                 "git-enviar": (self.config(operacoes={"fundacao": {}, "git-enviar": {}}), "1.7.11"),
                 "executar": (self.config(operacoes={"fundacao": {}, "executar": {}}), "1.7.11"),
                 "outra operação": (self.config(operacoes={"fundacao": {}, "outra": {}}), "exatamente"),
                 "lista": ([self.config()], "esquema")}
        for nome, (cfg, trecho) in casos.items():
            with self.subTest(caso=nome):
                with self.assertRaises(self.mod.Recusa) as ctx:
                    self.mod.carregar_config(self.gravar(cfg))
                self.assertIn(trecho, str(ctx.exception))

    def test_chave_repetida_json_ilegivel_e_arquivo_grande_recusados(self):
        texto = json.dumps(self.config())
        for nome, dados in (("repetida", (texto[:-1] + ', "projeto": "proj-b"}').encode("utf-8")),
                            ("lixo", b"\xff\xfe nada"), ("grande", b" " * (self.mod.TETO_CONFIG + 1) + b"{}")):
            with self.subTest(caso=nome), self.assertRaises(self.mod.Recusa):
                self.mod.carregar_config(self.gravar(dados))

    def test_configuracao_por_ligacao_recusada(self):
        real = self.gravar(self.config())
        link = self.base / "etc" / "atalho.json"
        try:
            link.symlink_to(real)
        except OSError as exc:
            self.skipTest(f"link simbólico de arquivo indisponível: {exc}")
        with self.assertRaises(self.mod.Recusa):
            self.mod.carregar_config(link)

    def test_conferir_pela_linha_de_comando(self):
        arq = self.gravar(self.config())
        r = subprocess.run([sys.executable, "-I", "-B", str(PORTEIRO), "conferir", "--config", str(arq)],
                           capture_output=True, text=True, encoding="utf-8", env=ENV, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        res = json.loads(r.stdout)
        self.assertTrue(res["ok"])
        self.assertEqual(res["kit_sha256_encontrado"], res["kit_sha256_esperado"])
        with open(self.raiz / "fundacao" / "__main__.py", "a", encoding="utf-8") as f:
            f.write("# trocado depois do preparo\n")
        r = subprocess.run([sys.executable, "-I", "-B", str(PORTEIRO), "conferir", "--config", str(arq)],
                           capture_output=True, text=True, encoding="utf-8", env=ENV, timeout=60)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        res = json.loads(r.stdout)
        self.assertFalse(res["ok"])
        self.assertNotEqual(res["kit_sha256_encontrado"], res["kit_sha256_esperado"])
        self.assertIn("refaça o preparo", res["motivo"])


class TestHashDoKit(PorteiroCase):
    def test_hash_estavel_e_sensivel_a_conteudo_nome_e_arquivo_novo(self):
        h = self.mod.sha256_do_kit(self.raiz)
        self.assertEqual(h, self.mod.sha256_do_kit(self.raiz))
        principal = self.raiz / "fundacao" / "__main__.py"
        principal.write_text(principal.read_text(encoding="utf-8") + " ", encoding="utf-8")
        h2 = self.mod.sha256_do_kit(self.raiz)
        self.assertNotEqual(h, h2)
        (self.raiz / "fundacao" / "core" / "novo.py").write_text("", encoding="utf-8")
        h3 = self.mod.sha256_do_kit(self.raiz)
        self.assertNotEqual(h2, h3)
        (self.raiz / "fundacao" / "core" / "novo.py").rename(self.raiz / "fundacao" / "core" / "outro.py")
        self.assertNotEqual(h3, self.mod.sha256_do_kit(self.raiz))

    def test_pycache_fica_de_fora_e_pyc_solto_entra(self):
        h = self.mod.sha256_do_kit(self.raiz)
        cache = self.raiz / "fundacao" / "core" / "__pycache__"
        cache.mkdir()
        (cache / "db.cpython-312.pyc").write_bytes(b"bytecode qualquer")
        self.assertEqual(h, self.mod.sha256_do_kit(self.raiz), "o porteiro nunca lê __pycache__")
        (self.raiz / "fundacao" / "core" / "plantado.pyc").write_bytes(b"bytecode qualquer")
        self.assertNotEqual(h, self.mod.sha256_do_kit(self.raiz), ".pyc fora do __pycache__ rodaria como módulo")

    def test_ligacao_dentro_do_kit_e_kit_ausente_recusam(self):
        with self.assertRaises(self.mod.Recusa):
            self.mod.sha256_do_kit(self.base / "nao-existe")
        fora = self.base / "fora"
        fora.mkdir()
        (fora / "x.py").write_text("print('de fora')\n", encoding="utf-8")
        criar_ligacao_dir(self.raiz / "fundacao" / "ligado", fora)
        with self.assertRaises(self.mod.Recusa):
            self.mod.sha256_do_kit(self.raiz)

    @unittest.skipUnless(os.name == "posix", "nome de arquivo com bytes fora do UTF-8: só no POSIX")
    def test_nome_fora_do_utf8_ou_com_controle_no_kit_recusa_sem_traceback(self):
        arq = self.gravar(self.config())  # o hash esperado é o da árvore antes do nome ruim
        kit = os.fsencode(self.raiz / "fundacao")
        for nome, trecho in ((b"\xff.py", "UTF-8"), (b"a\nb.py", "controle")):
            with self.subTest(nome=nome):
                try:
                    with open(os.path.join(kit, nome), "wb") as f:
                        f.write(b"# plantado\n")
                except OSError as exc:
                    self.skipTest(f"o sistema de arquivos recusou o nome: {exc}")
                with self.assertRaises(self.mod.Recusa) as ctx:
                    self.mod.sha256_do_kit(self.raiz)
                self.assertIn(trecho, str(ctx.exception))
                r = subprocess.run([sys.executable, "-I", "-B", str(PORTEIRO), "conferir", "--config", str(arq)],
                                   capture_output=True, text=True, encoding="utf-8", env=ENV, timeout=60)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertNotIn("Traceback", r.stderr)
                res = json.loads(r.stdout)
                self.assertFalse(res["ok"])
                self.assertIn(trecho, res["motivo"])
                os.unlink(os.path.join(kit, nome))

    def test_copia_conferida_tem_os_bytes_do_hash_e_sai_quando_nao_confere(self):
        esperado = self.mod.sha256_do_kit(self.raiz)
        cache = self.raiz / "fundacao" / "core" / "__pycache__"
        cache.mkdir()
        (cache / "auth.cpython-312.pyc").write_bytes(b"bytecode qualquer")
        trabalho = self.base / "trabalho"
        trabalho.mkdir()
        pacote = Path(self.mod.kit_conferido(self.raiz, esperado, str(trabalho)))
        self.assertEqual((pacote.name, pacote.parent.parent), ("fundacao", trabalho))
        self.assertEqual(self.mod.sha256_do_kit(pacote.parent), esperado, "a cópia tem exatamente os bytes do hash")
        self.assertFalse((pacote / "core" / "__pycache__").exists(), "bytecode da raiz não vai para a cópia")
        self.assertEqual((pacote / "__main__.py").read_bytes(), (self.raiz / "fundacao" / "__main__.py").read_bytes())
        shutil.rmtree(pacote.parent)
        with self.assertRaises(self.mod.KitAlterado):
            self.mod.kit_conferido(self.raiz, "0" * 64, str(trabalho))
        fora = self.base / "fora"
        fora.mkdir()
        criar_ligacao_dir(self.raiz / "fundacao" / "ligado", fora)
        with self.assertRaises(self.mod.KitAlterado):  # árvore recusada também é passageira (não vira permanente)
            self.mod.kit_conferido(self.raiz, esperado, str(trabalho))
        self.assertEqual(list(trabalho.iterdir()), [], "a cópia que não confere não fica na pasta de trabalho")


class TestTetoDoKit(PorteiroCase):
    """Correção do lote 2: a cópia conferida grava cada byte antes de o hash fechar; o teto, conferido por fluxo, barra
    o arquivo plantado na raiz antes de ele ir para o disco."""

    def contar_gravados(self):
        gravados, gravar = [], os.write

        def contar(fd, dados):
            n = gravar(fd, dados)
            gravados.append(n)
            return n
        return gravados, mock.patch.object(self.mod.os, "write", side_effect=contar)

    def test_arquivo_acima_do_teto_recusado_antes_de_ir_para_a_copia(self):
        arq = self.gravar(self.config())  # o hash esperado é o da árvore sem o arquivo grande
        esperado = self.mod.sha256_do_kit(self.raiz)
        with open(self.raiz / "fundacao" / "core" / "plantado.bin", "wb") as f:
            f.truncate(17 << 20)  # 17 MiB (esparso onde o sistema de arquivos deixa)
        trabalho = self.base / "trabalho"
        trabalho.mkdir()
        gravados, contando = self.contar_gravados()
        with contando, self.assertRaises(self.mod.KitAlterado) as ctx:
            self.mod.kit_conferido(self.raiz, esperado, str(trabalho))
        self.assertIn("teto", str(ctx.exception))
        self.assertLess(sum(gravados), 1 << 20, "o arquivo acima do teto foi para a cópia")
        self.assertEqual(list(trabalho.iterdir()), [], "nada ficou na pasta de trabalho")
        r = subprocess.run([sys.executable, "-I", "-B", str(PORTEIRO), "conferir", "--config", str(arq)],
                           capture_output=True, text=True, encoding="utf-8", env=ENV, timeout=60)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("teto", json.loads(r.stdout)["motivo"])

    def test_itens_demais_recusados(self):
        esperado = self.mod.sha256_do_kit(self.raiz)
        with mock.patch.object(self.mod, "TETO_KIT_ITENS", 4):  # o kit fictício: 3 arquivos e a pasta core
            self.assertEqual(self.mod.sha256_do_kit(self.raiz), esperado, "no teto ainda vale")
            for nome, criar in (("arquivo", lambda p: p.write_text("", encoding="utf-8")), ("pasta", Path.mkdir)):
                with self.subTest(item=nome):
                    item = self.raiz / "fundacao" / "core" / f"a-mais-{nome}"
                    criar(item)
                    with self.assertRaises(self.mod.Recusa) as ctx:
                        self.mod.sha256_do_kit(self.raiz)
                    self.assertIn("teto", str(ctx.exception))
                    (item.rmdir if item.is_dir() else item.unlink)()

    def test_arquivo_que_cresce_ou_passa_do_que_resta_para_antes_de_gravar(self):
        fonte = self.base / "cresce.py"
        fonte.write_bytes(b"x" * (3 << 20))
        fstat = os.fstat

        def tamanho_da_abertura(fd):  # na abertura o arquivo tinha 1000 bytes: cresceu depois
            st = fstat(fd)
            return os.stat_result((st.st_mode, st.st_ino, st.st_dev, st.st_nlink, st.st_uid, st.st_gid, 1000,
                                   st.st_atime, st.st_mtime, st.st_ctime))
        destino = self.base / "copia-1.py"
        with mock.patch.object(self.mod.os, "fstat", side_effect=tamanho_da_abertura):
            with self.assertRaises(self.mod.Recusa) as ctx:
                self.mod._ler_e_copiar(str(fonte), "cresce.py", str(destino), self.mod.TETO_KIT_BYTES)
        self.assertIn("cresceu", str(ctx.exception))
        self.assertEqual(destino.stat().st_size, 0, "o bloco a mais não foi para a cópia")
        destino = self.base / "copia-2.py"
        with self.assertRaises(self.mod.Recusa) as ctx:  # maior que o que ainda cabe no teto: nem abre a cópia
            self.mod._ler_e_copiar(str(fonte), "cresce.py", str(destino), 1 << 20)
        self.assertIn("teto", str(ctx.exception))
        self.assertFalse(destino.exists())
        sha, lidos = self.mod._ler_e_copiar(str(fonte), "cresce.py", str(destino), self.mod.TETO_KIT_BYTES)
        self.assertEqual((sha, lidos), (hashlib.sha256(fonte.read_bytes()).hexdigest(), 3 << 20))
        self.assertEqual(destino.read_bytes(), fonte.read_bytes())

    def test_leitura_lenta_do_kit_segue_renovando_o_sinal_de_vida(self):
        """Correção do lote 2: a árvore lenta de ler (DrvFs) não deixa o cliente desistir com "pode ter rodado"."""
        esperado = self.mod.sha256_do_kit(self.raiz)
        ler = self.mod._ler_e_copiar

        def devagar(*args):
            time.sleep(0.4)
            return ler(*args)
        chamadas = []
        with mock.patch.object(self.mod, "_ler_e_copiar", side_effect=devagar):
            self.assertEqual(self.mod.sha256_do_kit(self.raiz, durante=lambda: chamadas.append(1)), esperado)
        self.assertGreaterEqual(len(chamadas), 1, "a leitura de 1,2 s não chamou `durante`")


class TestIdadeDoPedido(PorteiroCase):
    """Correção do lote 2: o pedido que esperou mais que a idade máxima (fila e vez do banco) não roda."""

    def pedido(self, idade_s: float, agora: datetime) -> dict:
        return {"criado_em": (agora - timedelta(seconds=idade_s)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")}

    def test_a_espera_e_o_prazo_do_kit_cabem_no_corte_do_bash(self):
        self.assertLessEqual(self.mod.IDADE_MAXIMA_S + self.mod.PRAZO_KIT_S, self.mod.ORCAMENTO_S)
        self.assertLess(self.mod.ORCAMENTO_S, 120, "a ferramenta Bash corta em 120 s por padrão")
        self.assertLessEqual(self.mod.ESPERA_VEZ_S, self.mod.IDADE_MAXIMA_S, "a vez não é esperada além da idade")

    def test_pedido_vencido_ou_adiantado_nao_roda(self):
        agora = datetime.now(timezone.utc)
        antes = time.monotonic()
        limite = self.mod.limite_do_pedido(self.pedido(2, agora), agora)
        self.assertAlmostEqual(limite - antes, self.mod.IDADE_MAXIMA_S - 2, delta=1)
        antes = time.monotonic()
        limite = self.mod.limite_do_pedido(self.pedido(-self.mod.ADIANTADO_S + 1, agora), agora)  # adiantado: passa
        self.assertLessEqual(limite - antes, self.mod.IDADE_MAXIMA_S + 0.5, "o adiantado não ganha espera a mais")
        for idade, trecho in ((3600, "esperou"), (self.mod.IDADE_MAXIMA_S + 1, "esperou"), (-60, "futuro")):
            with self.subTest(idade=idade):
                with self.assertRaises(self.mod.Recusa) as ctx:
                    self.mod.limite_do_pedido(self.pedido(idade, agora), agora)
                self.assertIn(trecho, str(ctx.exception))
                self.assertIn("não rodou", str(ctx.exception))


class TestTravaDoBancoSemSobra(PorteiroCase):
    def test_renovacao_que_falha_nao_deixa_temporario_e_espera_para_tentar_de_novo(self):
        estado = self.raiz / "state"
        estado.mkdir()
        local = self.base / "local"
        local.mkdir()
        trava = self.mod.TravaDoBanco(str(self.raiz), local)
        trava.segura, trava.desde = True, self.mod.agora_iso()
        trocas = []

        def troca_que_falha(*args, **kwargs):
            trocas.append(args)
            raise PermissionError(13, "marcador aberto por outro processo (simulado)")
        with mock.patch.object(self.mod.os, "replace", side_effect=troca_que_falha):
            self.assertIn("não deu para renovar", trava.renovar(forcar=True))
            for _ in range(20):  # as voltas do laço do porteiro e as chamadas de `durante`
                self.assertIsNone(trava.renovar())
        self.assertEqual(len(trocas), 1, "a próxima tentativa espera RETENTAR_S segundos")
        with mock.patch.object(self.mod.os, "write", side_effect=OSError(28, "disco cheio (simulado)")):
            self.assertIn("não deu para renovar", trava.renovar(forcar=True))
        self.assertEqual([p.name for p in estado.iterdir()], [], "nenhum temporário sobrou em state/")
        self.assertIsNone(trava.renovar(forcar=True))
        self.assertEqual([p.name for p in estado.iterdir()], [self.mod.MARCADOR])


class TestPastasDeTrabalhoEmUso(PorteiroCase):
    """Reconferência 3 do lote 2: na partida, a pasta trabalho-* que um processo ainda usa (o kit órfão de um porteiro
    morto por SIGKILL, pela pasta atual ou por um argumento) fica, e com /proc ilegível nenhuma sai, como no
    limpar-porteiro do HOST. Aqui com um /proc de ensaio (também no Windows); com processos de verdade, no Linux, em
    test_porteiro_fila.py."""

    def setUp(self):
        super().setUp()
        self.privada = self.base / "privada"
        for nome in ("trabalho-aaaa1111", "trabalho-bbbb2222"):
            (self.privada / nome / "kit-x" / "fundacao").mkdir(parents=True)
        (self.privada / "registro.jsonl").write_text("{}\n", encoding="utf-8")  # o que não é trabalho-* não sai
        self.proc = self.base / "proc"
        self.proc.mkdir()

    def processo(self, pid: str, *args: str) -> Path:
        pasta = self.proc / pid
        pasta.mkdir()
        (pasta / "cmdline").write_bytes(b"".join(a.encode("utf-8") + b"\0" for a in args))
        return pasta

    def nomes(self) -> list[str]:
        return sorted(p.name for p in self.privada.iterdir())

    def test_proc_ilegivel_nada_sai(self):
        res = self.mod._limpar_trabalho_antigo(self.privada, proc=str(self.base / "sem-proc"))
        self.assertEqual(self.nomes(), ["registro.jsonl", "trabalho-aaaa1111", "trabalho-bbbb2222"])
        self.assertEqual((res["apagadas"], res["mantidas"]), ([], ["trabalho-aaaa1111", "trabalho-bbbb2222"]))
        self.assertIn("/proc ilegível", res["motivo"])
        self.assertIn("na dúvida, nada sai", res["motivo"])

    def test_pasta_citada_num_argumento_fica_e_a_livre_sai(self):
        usada = self.privada / "trabalho-aaaa1111"
        self.processo("4242", "/usr/bin/python3", "-I", "-X", f"pycache_prefix={usada}", "-c", "...")  # a pasta exata
        self.processo("77", "/bin/ls", f"{self.privada / 'trabalho-bbbb2222'}x")  # nome que só começa igual: não é ela
        (self.proc / "88").mkdir()  # o processo que saiu durante a leitura (nada para ler)
        self.processo("self", "/bin/sh", str(self.privada / "trabalho-bbbb2222"))  # não é pid: não conta
        self.processo("²", "/bin/sh", str(self.privada / "trabalho-bbbb2222"))  # dígito fora do ASCII: nem pid nem erro
        res = self.mod._limpar_trabalho_antigo(self.privada, proc=str(self.proc))
        self.assertEqual(self.nomes(), ["registro.jsonl", "trabalho-aaaa1111"])
        self.assertEqual((res["apagadas"], res["mantidas"]), (["trabalho-bbbb2222"], ["trabalho-aaaa1111"]))
        self.assertIn("trabalho-aaaa1111 (em uso pelo processo 4242", res["motivo"])
        self.assertTrue((usada / "kit-x" / "fundacao").is_dir(), "a cópia em uso ficou inteira")

    @unittest.skipUnless(os.name == "posix", "a pasta atual do /proc de ensaio é um link simbólico: só no POSIX")
    def test_pasta_atual_dentro_dela_fica(self):
        os.symlink(self.privada / "trabalho-bbbb2222" / "kit-x", self.processo("4343", "sleep", "60") / "cwd")
        os.symlink(self.base, self.processo("4444", "sleep", "60") / "cwd")  # pasta atual fora dela: não conta
        res = self.mod._limpar_trabalho_antigo(self.privada, proc=str(self.proc))
        self.assertEqual((res["apagadas"], res["mantidas"]), (["trabalho-aaaa1111"], ["trabalho-bbbb2222"]))
        self.assertIn("processo 4343", res["motivo"])
        self.assertNotIn("4444", res["motivo"])

    def test_sem_ninguem_usando_todas_saem_sem_motivo(self):
        self.processo("4545", "/bin/sh", "-c", "true")
        res = self.mod._limpar_trabalho_antigo(self.privada, proc=str(self.proc))
        self.assertEqual(self.nomes(), ["registro.jsonl"])
        self.assertEqual(res, {"apagadas": ["trabalho-aaaa1111", "trabalho-bbbb2222"], "mantidas": [], "motivo": None})


class TestLinhaDeComando(PorteiroCase):
    def test_pid_do_lancador_invalido_recusado(self):
        arq = self.gravar(self.config())
        for pid in ("0", "1", "-1"):
            with self.subTest(pid=pid):
                r = subprocess.run([sys.executable, "-I", "-B", str(PORTEIRO), "servir", "--config", str(arq),
                                    "--fila", str(self.proj / ".porteiro"), "--pid-lancador", pid],
                                   capture_output=True, text=True, encoding="utf-8", env=ENV, timeout=60)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("pid do lançador inválido", json.loads(r.stderr)["error"]["message"])
        self.assertFalse((self.proj / ".porteiro").exists(), "nada foi criado")
        for pid in (0, 1, -1):
            self.assertFalse(self.mod.processo_vivo(pid), pid)

    def test_pid_acima_do_pid_t_ou_do_pid_max_recusado_sem_traceback(self):
        """Correção do lote 2: acima do pid_t, os.kill levantava OverflowError e o `servir` saía com código 1."""
        arq = self.gravar(self.config())
        casa = self.base / "casa"  # se a recusa falhar, o porteiro grava na casa de ensaio, nunca na de verdade
        casa.mkdir()
        for pid in (2 ** 32, 2 ** 31, None):  # acima do pid_t (o OverflowError da revisão); depois, do pid_max
            pid = self.mod.PID_MAXIMO + 1 if pid is None else pid
            with self.subTest(pid=pid):
                r = subprocess.run([sys.executable, "-I", "-B", str(PORTEIRO), "servir", "--config", str(arq),
                                    "--fila", str(self.proj / ".porteiro"), "--pid-lancador", str(pid)],
                                   capture_output=True, text=True, encoding="utf-8", env={**ENV, "HOME": str(casa)},
                                   timeout=60)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertNotIn("Traceback", r.stderr)
                self.assertIn("pid do lançador inválido", json.loads(r.stderr)["error"]["message"])
            self.assertFalse((self.proj / ".porteiro").exists(), "nada foi criado")
            self.assertFalse(self.mod.processo_vivo(pid), pid)  # nem chega ao os.kill (no Windows, ele mataria)


class TestPedidoTipado(PorteiroCase):
    def kit(self, argv: list[str]) -> list[str]:
        return self.mod.argv_do_kit(argv, self.config())

    def test_mapa_monta_o_argv_do_kit_com_a_raiz_da_configuracao(self):
        r = str(self.raiz)
        decisao = os.path.realpath(self.proj / "decisoes" / "d.json")
        casos = [(["status"], ["--raiz", r, "status"]),
                 (["tarefa", "criar", "--projeto", "proj-a", "--objetivo=-começa com hífen"],
                  ["--raiz", r, "tarefa", "criar", "--projeto=proj-a", "--objetivo=-começa com hífen"]),
                 (["tarefa", "concluir", "--decisao", "decisoes/d.json"],
                  ["--raiz", r, "tarefa", "concluir", "--decisao=" + decisao]),
                 (["decisao", "registrar", "--arquivo", decisao], ["--raiz", r, "decisao", "registrar",
                                                                    "--arquivo=" + decisao]),
                 (["memoria", "licao", "consultar", "--projeto", "proj-a", "--gatilho", "prazo fictício"],
                  ["--raiz", r, "memoria", "licao", "consultar", "--projeto=proj-a", "--gatilho=prazo fictício"]),
                 (["abertura", "vigente", "--projeto", "proj-a", "--json"],
                  ["--raiz", r, "abertura", "vigente", "--projeto=proj-a", "--json"]),
                 (["conhecimento", "buscar", "--projeto=proj-a", "--consulta", "a=b c"],
                  ["--raiz", r, "conhecimento", "buscar", "--projeto=proj-a", "--consulta=a=b c"])]
        for entrada, saida in casos:
            with self.subTest(entrada=entrada[:2]):
                self.assertEqual(self.kit(entrada), saida)

    def test_subcomando_fora_do_mapa_recusado(self):
        casos = [["init", "--admin", "x"], ["projeto", "listar"], ["acl", "registrar", "--principal", "x"],
                 ["componente", "listar"], ["backup", "criar", "--destino", "x"], ["rota", "gasto", "--rota", "x"],
                 ["copia-assinatura", "preparar", "--projeto", "proj-a"], ["banco", "destravar", "--confirmar"],
                 ["memoria", "licao", "aprovar", "--memoria", "m", "--hash", "h"],
                 ["memoria", "licao", "revisar", "--memoria", "m"], ["memoria", "licao", "retirar", "--memoria", "m"],
                 ["tarefa", "apagar"], ["status", "a-mais"], ["status", "--help"], ["-h"], [],
                 ["abertura", "vigente", "--area", "/etc/fundacao-ia/projetos/proj-a/ficha"]]
        for argv in casos:
            with self.subTest(argv=argv), self.assertRaises(self.mod.Recusa):
                self.kit(argv)

    def test_raiz_ancora_e_abreviacao_recusadas(self):
        r = str(self.raiz)
        casos = [["--raiz", r, "status"], ["--raiz=" + r, "status"], ["status", "--raiz", r], ["--ra", r, "status"],
                 ["tarefa", "concluir", "--decisao", "decisoes/d.json", "--ancora", "a"],
                 ["decisao", "conferir-ancora", "--ancora=a"], ["tarefa", "criar", "--proj", "proj-a"],
                 ["tarefa", "criar", "--projeto", "proj-a", "--objet", "x"], ["decisao", "verificar", "--arq", "d"]]
        for argv in casos:
            with self.subTest(argv=argv), self.assertRaises(self.mod.Recusa):
                self.kit(argv)

    def test_outro_projeto_e_caminho_fora_recusados(self):
        casos = [["tarefa", "criar", "--projeto", "proj-b", "--objetivo", "x"],
                 ["conhecimento", "listar", "--projeto=proj-b"],
                 ["decisao", "verificar", "--arquivo", "../proj-b/decisoes/x.json"],
                 ["decisao", "verificar", "--arquivo", str(self.raiz / "state" / "state.sqlite")],
                 ["eventos", "exportar", "--destino", str(self.base / "fora.jsonl")]]
        for argv in casos:
            with self.subTest(argv=argv), self.assertRaises(self.mod.Recusa):
                self.kit(argv)

    def test_eventos_e_historico_fora_do_mapa_na_1710(self):
        """Emenda E2 dos contratos: leitura que pode mostrar o que não é do projeto sai do mapa (volta na 1.7.11 só com
        leitura restrita ao projeto); recusada mesmo com caminho dentro do projeto."""
        for argv in (["eventos", "verificar"], ["eventos", "exportar", "--destino", "outputs/e.jsonl"],
                     ["memoria", "licao", "historico", "--memoria", "m"]):
            with self.subTest(argv=argv):
                with self.assertRaises(self.mod.Recusa) as ctx:
                    self.kit(argv)
                self.assertIn("fora do mapa", str(ctx.exception))
        self.assertNotIn("eventos", self.mod.MAPA)
        self.assertNotIn("historico", self.mod.MEMORIA)

    def test_abertura_com_as_opcoes_de_cada_acao(self):
        """Item I3 da integração: cada ação da `abertura` só com as opções dela (as do cli_aberturas), sem --arquivo.
        Contraprova: o mapa anterior aceitava todas as recusas abaixo, salvo as três últimas."""
        r = str(self.raiz)
        (self.proj / "outputs").mkdir()
        rascunho = os.path.realpath(self.proj / "outputs" / "r.json")
        casos = [(["abertura", "preparar", "--projeto", "proj-a", "--rascunho", "outputs/r.json"],
                  ["--raiz", r, "abertura", "preparar", "--projeto=proj-a", "--rascunho=" + rascunho]),
                 (["abertura", "verificar", "--projeto", "proj-a", "--versao", "2"],
                  ["--raiz", r, "abertura", "verificar", "--projeto=proj-a", "--versao=2"]),
                 (["abertura", "verificar", "--projeto=proj-a"],
                  ["--raiz", r, "abertura", "verificar", "--projeto=proj-a"]),
                 (["abertura", "vigente", "--projeto", "proj-a"],
                  ["--raiz", r, "abertura", "vigente", "--projeto=proj-a"])]
        for entrada, saida in casos:
            with self.subTest(entrada=entrada[1:]):
                self.assertEqual(self.kit(entrada), saida)
        recusas = [["abertura", "preparar", "--projeto", "proj-a", "--rascunho", "outputs/r.json", "--arquivo",
                    "decisoes/d.json"],
                   ["abertura", "preparar", "--projeto", "proj-a", "--arquivo", "outputs/r.json"],
                   ["abertura", "preparar", "--projeto", "proj-a", "--rascunho", "outputs/r.json", "--versao", "3"],
                   ["abertura", "preparar", "--projeto", "proj-a", "--rascunho", "outputs/r.json", "--json"],
                   ["abertura", "verificar", "--projeto", "proj-a", "--rascunho", "outputs/r.json"],
                   ["abertura", "verificar", "--projeto", "proj-a", "--json"],
                   ["abertura", "vigente", "--projeto", "proj-a", "--versao", "2"],
                   ["abertura", "vigente", "--projeto", "proj-a", "--rascunho", "outputs/r.json"],
                   ["abertura", "preparar", "--projeto", "proj-b", "--rascunho", "outputs/r.json"],
                   ["abertura", "preparar", "--projeto", "proj-a", "--rascunho", "../proj-b/decisoes/x.json"],
                   ["abertura"]]
        for argv in recusas:
            with self.subTest(argv=argv[1:]), self.assertRaises(self.mod.Recusa):
                self.kit(argv)

    def test_ligacao_no_projeto_para_fora_recusada(self):
        fora = self.base / "outro-projeto"
        fora.mkdir()
        criar_ligacao_dir(self.proj / "atalho", fora)
        with self.assertRaises(self.mod.Recusa):
            self.kit(["decisao", "verificar", "--arquivo", "atalho/d.json"])

    def test_caractere_nulo_e_argv_fora_da_forma(self):
        for argv in (["tarefa", "criar", "--objetivo", "a\0b"], "status", ["status", 1], None):
            with self.subTest(argv=argv), self.assertRaises(self.mod.Recusa):
                self.kit(argv)


class TestFormato(PorteiroCase):
    ID = "0123456789abcdef0123456789abcdef"

    def pedido(self, **mudar) -> bytes:
        return json.dumps({"versao": 1, "id": self.ID, "op": "fundacao", "argv": ["status"],
                           "criado_em": "2026-10-31T12:00:00.000000Z", **mudar}).encode("utf-8")

    def test_pedido_valido_e_cada_desvio(self):
        self.assertEqual(self.mod.validar_pedido(self.pedido(), self.ID)["argv"], ["status"])
        sem_op = json.loads(self.pedido())
        del sem_op["op"]
        casos = {"campo a mais": self.pedido(extra=1), "campo a menos": json.dumps(sem_op).encode(),
                 "versão 2": self.pedido(versao=2), "versão booleana": self.pedido(versao=True),
                 "id de outro arquivo": self.pedido(id="f" * 32), "id maiúsculo": self.pedido(id=self.ID.upper()),
                 "op numérica": self.pedido(op=1), "argv texto": self.pedido(argv="status"),
                 "argv com número": self.pedido(argv=["status", 2]), "criado_em longo": self.pedido(criado_em="x" * 65),
                 "lista": b"[]", "utf-8 inválido": b"\xff\xfe", "chave repetida": self.pedido()[:-1] + b', "op": "x"}'}
        for nome, dados in casos.items():
            with self.subTest(caso=nome), self.assertRaises(self.mod.Recusa):
                self.mod.validar_pedido(dados, self.ID)

    def test_texto_fora_do_utf8_e_criado_em_fora_do_iso_utc(self):
        casos = {"substituto numa opção": self.pedido(argv=["tarefa", "criar", "--objetivo", "\ud800"]),
                 "substituto num caminho": self.pedido(argv=["decisao", "verificar", "--arquivo", "\udcff"]),
                 "substituto na op": self.pedido(op="\ud800"),
                 "criado_em sem fuso": self.pedido(criado_em="2026-10-31T12:00:00"),
                 "criado_em em outro fuso": self.pedido(criado_em="2026-10-31T12:00:00-03:00"),
                 "criado_em que não é data": self.pedido(criado_em="ontem à tarde")}
        for nome, dados in casos.items():
            with self.subTest(caso=nome):
                with self.assertRaises(self.mod.Recusa) as ctx:
                    self.mod.validar_pedido(dados, self.ID)
                self.assertIn("UTF-8" if "substituto" in nome else "criado_em", str(ctx.exception))
        for criado_em in ("2026-10-31T12:00:00.000000Z", "2026-10-31T12:00:00+00:00"):
            self.assertEqual(self.mod.validar_pedido(self.pedido(criado_em=criado_em), self.ID)["op"], "fundacao")

    def test_resposta_de_recusa_no_formato_que_o_cliente_aceita(self):
        r = self.mod.resposta_de_recusa(self.ID, self.mod.Recusa("motivo fictício"), 0.0)
        self.assertEqual(set(r), set(porteiro_cliente.CAMPOS_RESPOSTA))
        self.assertEqual((r["codigo"], r["truncado"], r["stdout"]), (2, False, ""))
        self.assertEqual(json.loads(r["stderr"])["error"], {"code": "E_PORTEIRO", "message": "motivo fictício"})

    def test_tetos_e_nomes_iguais_aos_do_cliente(self):
        self.assertEqual(self.mod.TETO_PEDIDO, porteiro_cliente.TETO_PEDIDO)
        self.assertEqual(self.mod.VIDA, porteiro_cliente.VIDA)
        # o escape do JSON multiplica por até 6 um byte de controle: a resposta com as saídas no teto ainda cabe
        self.assertLessEqual(6 * (self.mod.TETO_STDOUT + self.mod.TETO_STDERR) + 4096, porteiro_cliente.TETO_RESPOSTA)

    def test_ambiente_minimo_do_kit(self):
        amb = self.mod.ambiente_do_kit(self.config())
        esperado = {"FUNDACAO_RAIZ", "FUNDACAO_" + "PRINCIPAL", "FUNDACAO_PROJETO_TRAVADO",
                    "FUNDACAO_PORTEIRO_SERVIDOR", "FUNDACAO_ASSINANTE", "PATH"}
        self.assertEqual(set(amb) - {"WSL_DISTRO_NAME"}, esperado)
        self.assertEqual((amb["FUNDACAO_" + "PRINCIPAL"], amb["FUNDACAO_PROJETO_TRAVADO"], amb["PATH"]),
                         ("sessao-proj-a", "proj-a", "/usr/bin:/bin"))
        self.assertEqual((amb["FUNDACAO_PORTEIRO_SERVIDOR"], amb["FUNDACAO_ASSINANTE"]), ("1", "titular-ficticio"))


def _subparsers(parser: argparse.ArgumentParser) -> dict:
    return next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction)).choices


def _opcoes(parser: argparse.ArgumentParser) -> set:
    return {o for a in parser._actions for o in a.option_strings}


def _escolhas(parser: argparse.ArgumentParser, destino: str) -> set:
    return set(next(a for a in parser._actions if a.dest == destino).choices)


class TestMapaIgualAoDoKit(unittest.TestCase):
    def setUp(self):
        self.mod = carregar()

    def test_comandos_e_acoes_iguais_aos_do_modo_travado_do_kit(self):
        mapa = {c: (set(acoes) or None) for c, (acoes, *_r) in self.mod.MAPA.items()}
        mapa["memoria"] = set(self.mod.MEMORIA)
        self.assertEqual(mapa, COMANDOS_DA_TRAVA)

    def test_cada_opcao_do_mapa_existe_no_parser_do_kit(self):
        """Item I3 da integração: com `cli_aberturas` no laço das extensões (I2), nenhum comando do mapa falta no kit, e
        o teste desce nos subparsers das ações quando o kit os tem (`abertura preparar|verificar|vigente`, cada um com
        as opções dele). Antes, a `abertura` podia faltar, e as opções dela eram conferidas contra o parser de cima."""
        kit = _subparsers(build_parser())
        for comando, (acoes, opcoes, caminhos, sinais) in self.mod.MAPA.items():
            with self.subTest(comando=comando):
                self.assertIn(comando, kit)
                if acoes:
                    self.assertLessEqual(set(acoes), _escolhas(kit[comando], "acao"))
                if comando != "abertura":  # as da abertura ficam nos subparsers das ações (abaixo)
                    self.assertLessEqual(set(opcoes + caminhos + sinais), _opcoes(kit[comando]))
        do_kit = _subparsers(kit["abertura"])
        self.assertEqual(set(do_kit), set(self.mod.ABERTURA))
        for acao, (opcoes, caminhos, sinais) in self.mod.ABERTURA.items():
            with self.subTest(abertura=acao):
                self.assertLessEqual(set(opcoes + caminhos + sinais), _opcoes(do_kit[acao]))
                # e o que o kit tem a mais é só o que o porteiro recusa de propósito (--area do vigente)
                self.assertEqual(_opcoes(do_kit[acao]) - {"-h", "--help"} - set(opcoes + caminhos + sinais),
                                 {"--area"} if acao == "vigente" else set())
        licao = _subparsers(_subparsers(kit["memoria"])["licao"])
        for acao, opcoes in self.mod.MEMORIA.items():
            with self.subTest(memoria=acao):
                self.assertIn(acao, licao)
                self.assertLessEqual(set(opcoes), _opcoes(licao[acao]))

    def test_linha_da_abertura_no_mapa_e_a_uniao_das_acoes_sem_arquivo(self):
        acoes, opcoes, caminhos, sinais = self.mod.MAPA["abertura"]
        self.assertEqual(acoes, tuple(self.mod.ABERTURA))
        for i, parte in enumerate((opcoes, caminhos, sinais)):
            self.assertEqual(set(parte), {o for v in self.mod.ABERTURA.values() for o in v[i]})
        todas = {o for v in self.mod.ABERTURA.values() for parte in v for o in parte}
        self.assertNotIn("--arquivo", todas)  # o cli_aberturas não tem --arquivo
        self.assertNotIn("--area", todas)  # o kit travado a recusa; o porteiro também

    def test_todo_pedido_de_abertura_que_o_porteiro_aceita_o_kit_aceita(self):
        """Implicação sobre um conjunto de pedidos (as opções obrigatórias de cada ação mais cada combinação das
        outras): o argv que o porteiro monta para `abertura` passa no parser do kit. Com o mapa anterior (as opções das
        três ações juntas, e --arquivo), o porteiro aceitava `vigente --versao`, `verificar --rascunho`, `verificar
        --json` e `preparar --arquivo`, que o kit recusava (item I3 da integração)."""
        mod, base = self.mod, Path(tempfile.mkdtemp(prefix="porteiro-1710-i3-"))
        self.addCleanup(shutil.rmtree, base, True)
        raiz = base / "raiz"
        kit_ficticio(raiz)
        (raiz / "projects" / "proj-a" / "outputs").mkdir(parents=True)
        cfg = {"raiz": str(raiz), "projeto": "proj-a"}
        obrigatorias = {"preparar": ["--projeto", "proj-a", "--rascunho", "outputs/r.json"],
                        "verificar": ["--projeto", "proj-a"], "vigente": ["--projeto", "proj-a"]}
        outras = (["--versao", "2"], ["--rascunho", "outputs/r.json"], ["--json"], ["--arquivo", "outputs/r.json"],
                  ["--area", "outputs"])
        aceitos = []
        for acao, base_argv in obrigatorias.items():
            for n in range(1 << len(outras)):
                argv = ["abertura", acao, *base_argv, *(p for i, par in enumerate(outras) if n >> i & 1 for p in par)]
                try:
                    saida = mod.argv_do_kit(argv, cfg)
                except mod.Recusa:
                    continue
                aceitos.append(argv)
                with self.subTest(argv=argv), mock.patch("sys.stderr"):
                    try:
                        ns = build_parser().parse_args(saida)
                    except SystemExit:
                        self.fail(f"o kit recusa o que o porteiro aceitou: {saida}")
                    self.assertEqual((ns.comando, ns.acao), ("abertura", acao))
        # preparar (com e sem --rascunho repetido), verificar (com e sem --versao) e vigente (com e sem --json)
        self.assertEqual(len(aceitos), 6, aceitos)

    def test_caminhos_do_cliente_cobrem_os_do_mapa(self):
        caminhos = {o for (_a, _o, cs, _s) in self.mod.MAPA.values() for o in cs}
        self.assertEqual(caminhos, set(porteiro_cliente.OPCOES_DE_CAMINHO))


if __name__ == "__main__":
    unittest.main()
