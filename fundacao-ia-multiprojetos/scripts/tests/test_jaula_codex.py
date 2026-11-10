"""O Codex da jaula (1.7.11, lote L6; DESENHO-JAULA §6 e §8; itens 6 e 13 das respostas do titular de 08/11/2026).

U (qualquer sistema): o pedido do Codex (prompt, `acao`), o porteiro, o `config.toml` imposto, o pino do binário, o argv do
bubblewrap, a entrada fixa de ponta a ponta com a caixa, o proxy e o Codex falsos (N-CDX-1, 4 a 8), o `auth.json` e a
conferência de segredo, o download com SHA-256 conferido antes de instalar (arquivo falso), o lançador do titular e o passo 6c
do `preparar-wsl.sh`. L (só no Linux; pulam com o motivo quando falta o bwrap): o pty do terminal do Codex e o Codex falso
montado na caixa de verdade. Com `FUNDACAO_CI_EXIGE_BWRAP=1` a falta do bwrap FALHA em vez de pular. O M7 (sandbox próprio do
Codex na jaula, rede e segredo visíveis aos comandos, domínios, nomes de chave rodando) NÃO foi medido: aqui só a opção mais
segura e o consumidor da medida. Nomes, projetos e tokens fictícios."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import types
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from apoio import ENV, SKILL
from test_dominios_ficha import carregar_por_caminho
from test_host_projeto_apoio import carregar_preparo
from test_host_projeto_area import (USUARIO_DO_ENSAIO, VisudoFalso, ficha_aplicada, gravar_area, guardar_resposta_do_canario,
                                    secao_codex)
from test_jaula_bwrap import EXIGE, MOTIVO

try:
    import tomllib
except ImportError:  # Python < 3.11
    tomllib = None

WSL = SKILL / "assets" / "host" / "wsl"
J = carregar_por_caminho("_jaula_codex_teste", WSL / "jaula.py")
PJ = carregar_por_caminho("_porteiro_jaula_codex_teste", WSL / "porteiro_jaula.py")
HOJE = date(2026, 11, 8)
HASHES = {"jaula-entrar": "a" * 64, "proxy_lista.py": "b" * 64, "bwrap": "c" * 64}
TOKEN = "-".join(("tok", "ficticio", "0123456789", "ABCDEFGHIJ", "klmnop"))      # token inventado, 20 caracteres ou mais
RENOVA = "-".join(("ren", "ficticio", "9876543210", "ZYXWVUTSRQ", "abcdef"))
R55 = {"plano": "plano-teste", "treinamento_desligado": True, "conferido_em": "2026-11-08"}
# F1 (revisao de seguranca da 1.7.11): o Codex da SESSAO (codex-exec) so abre com a chave de API; a conta do ChatGPT so abre a
# janela do titular. ITEM/FICHA valem para os dois modos (chave de API); ITEM_CONTA/FICHA_CONTA, para a conta.
ITEM = {"provedor": "openai-codex", "autenticacao": "chave_api", "modos": ["exec", "titular"],
        "conteudo_de_terceiros": True, "teto_chamadas_dia": 30, "r55": R55}
ITEM_CONTA = {**ITEM, "autenticacao": "conta_chatgpt"}
FICHA = {"valida": True, "project_id": "criador", "outras_llm": [ITEM]}
FICHA_CONTA = {"valida": True, "project_id": "criador", "outras_llm": [ITEM_CONTA]}
RELATORIO = {"schema_version": J.ESQUEMA_RELATORIO_INSTALADO, "hashes": HASHES,
             "modos": {"codex-exec": {"aprovado": True}, "codex-titular": {"aprovado": True}}}


def pedido(**campos):
    base = {"schema_version": J.ESQUEMA_PEDIDO, "id": "pedido-cdx-0001"}
    base.update(campos)
    return json.dumps(base).encode()


def uma_vez(modo="codex-exec", **campos):
    return J.validar_pedido(pedido(**campos), "criador", modo)


class PedidoDoCodex(unittest.TestCase):
    def recusa(self, modo="codex-exec", **campos):
        with self.assertRaises(J.Recusa, msg=str(campos)[:80]):
            uma_vez(modo, **campos)

    def test_o_exec_pede_prompt_e_arquivos_e_o_prompt_tem_teto_em_bytes_e_sem_controle(self):
        self.assertEqual(uma_vez(prompt="resuma\ncom acentuação\t.", arquivos=["a.md"])["arquivos"], ["a.md"])
        self.recusa(arquivos=["a.md"])                                               # sem prompt
        for ruim in ("", 3, None, ["x"], "a\0b", "a\x1bb", "a\x7fb", "x" * (J.TETO_PROMPT_BYTES + 1),
                     "ç" * (J.TETO_PROMPT_BYTES // 2 + 1), "\ud800"):
            self.recusa(prompt=ruim, arquivos=["a.md"])
        self.assertEqual(len(uma_vez(prompt="x" * J.TETO_PROMPT_BYTES, arquivos=["a.md"])["prompt"]), J.TETO_PROMPT_BYTES)
        self.recusa(prompt="x", arquivos=["a.md"], comando=["sh"])                   # campo livre
        self.recusa("codex-titular", prompt="x")                                     # o prompt é só do exec

    def test_a_acao_do_titular_so_pode_ser_login_e_o_terminal_usa_o_pedido_padrao(self):
        self.assertEqual(uma_vez("codex-titular", acao="login")["acao"], "login")
        for ruim in ("tui", "", None, 1):
            self.recusa("codex-titular", acao=ruim)
        self.assertNotIn("acao", J.validar_pedido(None, "criador", "codex-titular"))
        self.recusa(acao="login", prompt="x", arquivos=["a.md"])                    # 'acao' não é campo do exec

    def test_f10_listar_e_trazer_pedem_o_id_da_retida_e_o_trazer_pede_o_sha256_da_lista(self):
        digest = "ab" * 32
        self.assertEqual(uma_vez("codex-titular", acao="listar", retida="t-20261109-abc123")["retida"], "t-20261109-abc123")
        boa = uma_vez("codex-titular", acao="trazer", retida="t-20261109-abc123", lista_sha256=digest)
        self.assertEqual(boa["lista_sha256"], digest)
        for ruim in ({"acao": "listar"}, {"acao": "listar", "retida": "../x"}, {"acao": "listar", "retida": "ABCDEFGH1"},
                     {"acao": "listar", "retida": 7}, {"acao": "listar", "retida": "t-20261109-abc123", "lista_sha256": digest},
                     {"acao": "trazer", "retida": "t-20261109-abc123"},
                     {"acao": "trazer", "retida": "t-20261109-abc123", "lista_sha256": "xyz"},
                     {"acao": "trazer", "retida": "t-20261109-abc123", "lista_sha256": digest.upper()},
                     {"acao": "login", "retida": "t-20261109-abc123"}, {"retida": "t-20261109-abc123"},
                     {"acao": "trazer", "retida": "t-20261109-abc123", "lista_sha256": digest, "arquivos": ["a.md"]},
                     {"acao": "apagar", "retida": "t-20261109-abc123"}):
            with self.subTest(ruim):
                self.recusa("codex-titular", **ruim)
        self.recusa(acao="listar", retida="t-20261109-abc123")                       # 'retida' não é campo do exec

    def test_o_porteiro_leva_so_prompt_e_arquivos_e_confere_o_tamanho_do_prompt(self):
        boa = {"prompt": "resuma", "arquivos": ["a.md"]}
        self.assertEqual(PJ.validar_carga("codex", boa), boa)
        for ruim in ({"arquivos": ["a.md"]}, {**boa, "prompt": ""}, {**boa, "prompt": 7}, {**boa, "prompt": "x" * (PJ.TETO_PROMPT_BYTES + 1)},
                     {**boa, "modo": "codex-titular"}, {**boa, "acao": "login"}, {**boa, "argv": ["sh"]}, {"prompt": "x"}):
            with self.subTest(list(ruim)), self.assertRaises(PJ.Recusa):
                PJ.validar_carga("codex", ruim)
        self.assertEqual(PJ.OPERACOES["codex"]["modo"], "codex-exec")                # o modo sai da tabela, nunca do pedido

    def test_n_cdx_1_sem_outras_llm_na_ficha_o_porteiro_recusa_e_nao_ha_linha_nem_lancador(self):
        cfg = {"schema_version": PJ.SCHEMA, "raiz": "/mnt/x/raiz", "projeto": "criador", "usuario_jaula": "fundacao-jaula",
               "entrada": "/usr/local/lib/fundacao-ia/jaula/1.7.11/jaula-entrar", "operacoes": {"navegador": {}}}
        chamadas = []
        with tempfile.TemporaryDirectory() as casa:
            p = PJ.PorteiroJaula(PJ.validar_config(cfg), None, casa=Path(casa), executar=lambda *a: chamadas.append(a))
            dados = json.dumps({"versao": 1, "id": "a" * 32, "op": "codex", "carga": {"prompt": "x", "arquivos": ["a.md"]},
                                "criado_em": PJ.agora_iso()}).encode()
            resposta, _ = p.atender("a" * 32, dados)
        self.assertEqual((resposta["codigo"], chamadas), (2, []))
        self.assertIn("não está aberta", resposta["stderr"])
        m = carregar_preparo()
        sem = ficha_aplicada(m)
        self.assertEqual((m.preparo_jaula().modos_da_ficha(sem), m.preparo_jaula().operacoes_da_sessao(sem)), ([], {}))
        self.assertIsNone(m.preparo_jaula().config_do_porteiro("/mnt/x/raiz", "criador", sem, "/usr/local/lib/x"))


class ConfigPinoEMedidas(unittest.TestCase):
    def test_o_modelo_tem_so_as_chaves_do_esquema_da_versao_fixada_e_as_opcoes_seguras(self):
        if tomllib is None:
            self.skipTest("tomllib só existe no Python 3.11 ou mais novo")
        # Chaves e valores conferidos em 08/11/2026 contra codex-rs/core/config.schema.json na etiqueta rust-v0.166.0
        # (analise/FONTE-CODEX-20261108.md). Mudar o modelo exige conferir o esquema da versão e mudar esta tabela.
        esperado = {"web_search": "disabled", "check_for_update_on_startup": False, "project_doc_max_bytes": 0,
                    "allow_login_shell": False, "cli_auth_credentials_store": "file",
                    "sandbox_workspace_write": {"network_access": False, "writable_roots": []},
                    "shell_environment_policy": {"inherit": "core", "ignore_default_excludes": False},
                    "analytics": {"enabled": False}, "feedback": {"enabled": False},
                    "otel": {"exporter": "none", "metrics_exporter": "none", "trace_exporter": "none"},
                    "history": {"persistence": "none"}, "projects": {"/trabalho/saida": {"trust_level": "untrusted"}}}
        for modo, aprovacao in (("codex-exec", "never"), ("codex-titular", "on-request")):
            dados = tomllib.loads(J.config_do_codex(modo, {}).decode("utf-8"))
            with self.subTest(modo=modo):
                funcoes = dados.pop("features")
                self.assertEqual(dados, {**esperado, "approval_policy": aprovacao, "sandbox_mode": "workspace-write"})
                self.assertTrue(funcoes and all(v is False for v in funcoes.values()))      # nenhum recurso novo ligado
                self.assertNotIn("mcp_servers", dados)                                       # nenhum servidor MCP
                self.assertEqual(sorted(funcoes), sorted(set(funcoes)))

    def test_o_sandbox_so_muda_pela_medida_do_relatorio_instalado_e_so_para_o_valor_conhecido(self):
        padrao = J.medidas_do_codex(RELATORIO, "codex-exec")
        self.assertEqual(padrao, {"sandbox_codex": "workspace-write"})                       # M7 não medida: a opção mais segura
        medido = {"modos": {"codex-exec": {"medidas": {"sandbox_codex": "danger-full-access"}}}}
        self.assertEqual(J.medidas_do_codex(medido, "codex-exec"), {"sandbox_codex": "danger-full-access"})
        self.assertEqual(J.medidas_do_codex(medido, "codex-titular"), padrao)                # a medida é por modo
        for lixo in (None, [], {"modos": []}, {"modos": {"codex-exec": {"medidas": {"sandbox_codex": "read-only"}}}},
                     {"modos": {"codex-exec": {"medidas": {"sandbox_codex": True}}}}, {"modos": {"codex-exec": 3}}):
            self.assertEqual(J.medidas_do_codex(lixo, "codex-exec"), padrao)
        texto = J.config_do_codex("codex-exec", {"sandbox_codex": "danger-full-access"}).decode("utf-8")
        self.assertIn('sandbox_mode = "danger-full-access"', texto)
        for ruim in ({"sandbox_codex": "read-only"}, {"sandbox_codex": "x\nweb_search = \"live\""}):
            with self.assertRaises(J.Recusa):
                J.config_do_codex("codex-exec", ruim)
        with self.assertRaises(J.Recusa):
            J.config_do_codex("navegador", {})

    def test_o_pino_e_a_release_estavel_com_tamanho_e_sha256_da_api_e_o_validador_recusa_o_resto(self):
        pins = J.pins_do_codex()
        self.assertEqual((pins["versao"], pins["etiqueta"], pins["arquivo"]),
                         ("0.166.0", "rust-v0.166.0", "codex-x86_64-unknown-linux-musl.tar.gz"))
        self.assertEqual((pins["tamanho"], pins["conferido_em"]), (121764138, "2026-11-08"))
        self.assertRegex(pins["sha256"], "^[0-9a-f]{64}$")
        self.assertIn("FONTE-CODEX-20261108", pins["fonte"])
        self.assertIsNone(J.problema_dos_pins(pins))
        for campo, valor in (("versao", "0.166"), ("versao", "0.166.0-alpha.1"), ("etiqueta", "rust-v0.167.0"),
                             ("arquivo", "codex-aarch64-unknown-linux-musl.tar.gz"), ("membro", "outro"), ("tamanho", 0),
                             ("tamanho", 601 << 20), ("tamanho", "1"), ("tamanho", True), ("sha256", pins["sha256"].upper()),
                             ("sha256", "a" * 63), ("schema_version", "fundacao.pins_codex/2")):
            with self.subTest(campo=campo, valor=valor):
                self.assertTrue(J.problema_dos_pins({**pins, campo: valor}))
        self.assertTrue(J.problema_dos_pins([]))
        cfg = J.Config(programas="/usr/local/lib/fundacao-ia/jaula/1.7.11")
        self.assertEqual(J.programa_do_codex(cfg), f"{cfg.programas}/codex/0.166.0/codex")


class ArgvDoCodex(unittest.TestCase):
    CFG = J.Config(estado="/var/lib/fundacao-ia/jaula", programas="/usr/local/lib/fundacao-ia/jaula/1.7.11", usuario=None)
    FDS = {d: 10 + i for i, d in enumerate(J.DADOS_GERADOS)}
    TRABALHO = "/var/lib/fundacao-ia/jaula/criador/trabalho/pedido-cdx-0001"

    def argv(self, modo, comando=("/x",), extras=None, existe=lambda p: True):
        perfil = J.perfil_do_modo(modo)
        fds = dict(self.FDS)
        if extras and any(n in perfil.segredos for n in extras):
            fds["args"] = 30
        a = J.montar_argv(self.CFG, "criador", "pedido-cdx-0001", perfil, list(comando), fds=fds, extras=extras, existe=existe,
                          sistema=[["ro-bind", "/usr", "/usr"]])
        return a[:a.index("--")], a[a.index("--") + 1:]

    def pares(self, a, opcao):
        return [a[i + 1:i + 3] for i, x in enumerate(a) if x == opcao]

    def test_o_exec_leva_o_prompt_pelo_descritor_e_nada_dele_no_argv_nem_no_ambiente_visivel(self):
        prompt = "pedido sigiloso do cliente " * 400                                    # bem acima de 4096 caracteres
        comando, extras = J.comando_do_codex(self.CFG, "codex-exec", {"prompt": prompt})
        self.assertNotIn("sigiloso", " ".join(comando))
        self.assertEqual(comando[:3], ["/bin/sh", "-c", J.SH_DO_PROMPT])               # o texto do sh é fixo
        self.assertNotIn("FUNDACAO_PROMPT=", J.SH_DO_PROMPT)
        self.assertEqual(comando[3], f"{self.CFG.programas}/codex/0.166.0/codex")
        for fixo in ("exec", "--strict-config", "--skip-git-repo-check", "--ephemeral", "--ignore-rules", "-C", "/trabalho/saida"):
            self.assertIn(fixo, comando)
        self.assertEqual(comando[-1], "-")                                              # o prompt entra pela entrada padrão
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", comando)
        self.assertNotIn("--ignore-user-config", comando)                               # o config.toml imposto tem de valer
        self.assertTrue(extras["FUNDACAO_PROMPT"].startswith(J.PREFACIO_DO_CODEX))
        self.assertTrue(extras["FUNDACAO_PROMPT"].endswith(prompt))
        antes, depois = self.argv("codex-exec", comando, extras)
        self.assertNotIn("sigiloso", " ".join(antes + depois))
        self.assertEqual(self.pares(antes, "--args")[0][0], "30")
        self.assertNotIn("FUNDACAO_PROMPT", {x[0] for x in self.pares(antes, "--setenv")})
        self.assertEqual(J.args_secretos({"FUNDACAO_PROMPT": "v"}), b"--setenv\0FUNDACAO_PROMPT\0v\0")
        with self.assertRaises(J.Recusa):                                               # o teto do valor secreto
            J.ambiente_do_modo(self.CFG, J.perfil_do_modo("codex-exec"), extras={"FUNDACAO_PROMPT": "x" * (41 * 1024)})
        with self.assertRaises(J.Recusa):                                               # os outros nomes seguem em 4096
            J.ambiente_do_modo(self.CFG, J.perfil_do_modo("codex-exec"), extras={"OPENAI_API_KEY": "x" * 4097})

    def test_montagens_do_codex_binario_e_config_so_leitura_e_nada_do_host(self):
        for modo in ("codex-exec", "codex-titular"):
            antes, _ = self.argv(modo)
            with self.subTest(modo=modo):
                self.assertIn("--disable-userns", antes)                                # sem namespace aninhado na jaula
                self.assertIn([f"{self.CFG.programas}/codex"] * 2, self.pares(antes, "--ro-bind"))
                config = [self.TRABALHO + "/codex-config.toml", "/home/jaula/codex/config.toml"]
                self.assertIn(config, self.pares(antes, "--ro-bind"))                    # só leitura
                self.assertNotIn(config, self.pares(antes, "--bind"))
                estado = antes.index("--bind", antes.index("/var/lib/fundacao-ia/jaula/criador/codex/home") - 1)
                self.assertLess(estado, antes.index(config[0]))                         # o config vem DEPOIS do CODEX_HOME montado
                self.assertIn([self.TRABALHO + "/projeto", "/trabalho/projeto"], self.pares(antes, "--ro-bind"))
                self.assertNotIn("/trabalho/projeto", [x[1] for x in self.pares(antes, "--bind")])
                self.assertFalse([x for x in antes if "/mnt" in x or "/data" in x or "projects/" in x])
        sem_arquivo, _ = self.argv("codex-exec", existe=lambda p: not p.endswith("codex-config.toml"))
        self.assertNotIn("/home/jaula/codex/config.toml", sem_arquivo)                  # a `entrar` recusa nesse caso (abaixo)

    def test_o_terminal_recebe_so_o_term_simples_e_o_titular_tem_pty_proprio(self):
        self.assertEqual(J.terminal_do_titular({"TERM": "xterm-256color"}), "xterm-256color")
        for ruim in ("", "x y", "a;b", "$(id)", "../x", "a" * 41, "é"):
            self.assertEqual(J.terminal_do_titular({"TERM": ruim}), "xterm-256color", ruim)
        self.assertEqual(J.terminal_do_titular({}), "xterm-256color")
        antes, _ = self.argv("codex-titular", extras={"TERM": "xterm"})
        self.assertIn(["TERM", "xterm"], self.pares(antes, "--setenv"))
        self.assertNotIn("--new-session", antes)                                        # o pty próprio é a sessão
        self.assertIn("--new-session", self.argv("codex-exec")[0])
        self.assertNotIn(["TERM", "xterm"], self.pares(self.argv("codex-exec", extras=None)[0], "--setenv"))
        with self.assertRaises(J.Recusa):
            self.argv("codex-exec", extras={"TERM": "xterm"})                           # o exec não recebe TERM

    def test_login_e_terminal_do_titular_nao_levam_prompt_nem_projeto(self):
        codex = f"{self.CFG.programas}/codex/0.166.0/codex"
        self.assertEqual(J.comando_do_codex(self.CFG, "codex-titular", {"acao": "login"}), ([codex, "login", "--device-auth"], {}))
        comando, extras = J.comando_do_codex(self.CFG, "codex-titular", {})
        self.assertEqual((comando[:2], extras), ([codex, "--strict-config"], {}))
        self.assertIn("--no-daemon", comando)
        login = J.perfil_do_modo("codex-titular", None, None, "login")
        self.assertEqual((login.projeto, login.saida, login.terminal), ("nenhum", None, True))
        self.assertEqual(J.perfil_do_modo("codex-titular").projeto, "inteiro")


class _Entrar(unittest.TestCase):
    """A entrada fixa de ponta a ponta, com o proxy, o bwrap, o pty e o Codex falsos (nada roda no Linux nem baixa)."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="jaula-cdx-1711-")).resolve()
        self.addCleanup(shutil.rmtree, self.base, True)
        self.estado_p = self.base / "estado" / "criador"
        self.home = self.estado_p / "codex" / "home"
        self.home.mkdir(parents=True)
        (self.estado_p / "proxy").mkdir()
        for pasta in (self.estado_p, self.estado_p / "codex", self.home):             # a entrada fixa exige 0700 (no Linux)
            os.chmod(pasta, 0o700)
        self.escrever_auth()
        self.raiz = self.base / "raiz"
        self.projeto = self.raiz / "projects" / "criador"
        for rel, dados in {"notas/a.md": b"nota", "AGENTS.md": b"instrucao plantada", ".codex/config.toml": b"plantado",
                           ".env": b"SEGREDO=1", "outputs/velho.txt": b"velho"}.items():
            (self.projeto / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.projeto / rel).write_bytes(dados)
        self.cfg = J.Config(bwrap="/usr/bin/bwrap", python="/usr/bin/python3", estado=str(self.base / "estado"),
                            programas=str(self.base / "prog"), etc=str(self.base / "etc"), usuario=None)
        self.ficha, self.relatorio = json.loads(json.dumps(FICHA)), json.loads(json.dumps(RELATORIO))
        self.rodadas, self.memfds, self.escreve, self.visto = [], {}, {}, {}
        self.stdout = b"resposta do Codex"
        ex = J._script("execucao_isolada")
        for alvo, novo in ((ex, ("_rodar", self.rodar_falso)), (J, ("rodar_com_pty", self.pty_falso)),
                           (J, ("subir_proxy", mock.Mock())), (J, ("parar_proxy", mock.Mock())),
                           (J, ("_resumo_do_proxy", mock.Mock(return_value={}))), (J, ("_memfd", self.memfd_falso))):
            p = mock.patch.object(alvo, *novo)
            p.start()
            self.addCleanup(p.stop)

    def escrever_auth(self, dados=None):
        arquivo = self.home / "auth.json"
        arquivo.write_text(json.dumps(dados or {"tokens": {"access_token": TOKEN, "refresh_token": RENOVA, "account_id": "conta-1"},
                                               "last_refresh": "2026-11-08T10:00:00.123456789Z"}), encoding="utf-8")
        os.chmod(arquivo, 0o600)

    def memfd_falso(self, nome, dados):
        self.memfds[nome] = dados
        return os.open(os.devnull, os.O_RDONLY)

    def fonte(self, argv, opcao, destino):
        return Path(next(argv[i + 1] for i, x in enumerate(argv) if x == opcao and argv[i + 2] == destino))

    def capturar(self, argv):
        """O que a caixa veria: o config.toml montado, a cópia do projeto e a pasta de saída (a de trabalho some no fim)."""
        self.rodadas.append(list(argv))
        for chave, opcao, destino in (("config", "--ro-bind", "/home/jaula/codex/config.toml"),):
            if destino in argv:
                self.visto[chave] = self.fonte(argv, opcao, destino).read_text(encoding="utf-8")
        if "/trabalho/projeto" in argv:
            pasta = self.fonte(argv, "--ro-bind", "/trabalho/projeto")
            self.visto["projeto"] = sorted(p.relative_to(pasta).as_posix() for p in pasta.rglob("*") if p.is_file())
        saida = self.fonte(argv, "--bind", "/trabalho/saida")
        for nome, dados in self.escreve.items():
            (saida / nome).parent.mkdir(parents=True, exist_ok=True)
            (saida / nome).write_bytes(dados)

    def rodar_falso(self, argv, cwd, env, lim, pass_fds=()):
        self.capturar(argv)
        return {"codigo": 0, "stdout": self.stdout, "stderr": b""}

    def pty_falso(self, argv, lim, pass_fds=()):
        self.capturar(argv)
        return {"codigo": 0, "stdout": b"", "stderr": b""}

    def comando(self, i=0):
        return self.rodadas[i][self.rodadas[i].index("--") + 1:]

    def entrar(self, modo="codex-exec", **campos):
        if modo == "codex-exec":
            campos = {"prompt": "resuma", "arquivos": ["notas/a.md"], **campos}
        return J.entrar(self.cfg, "criador", modo, pedido(**campos) if campos else None, raiz=str(self.raiz), ficha=self.ficha,
                        relatorio=self.relatorio, hoje=HOJE, hashes_atuais=HASHES)

    def nada_rodou(self):
        self.assertEqual(self.rodadas, [])
        self.assertFalse((self.estado_p / "trabalho").exists() and list((self.estado_p / "trabalho").iterdir()))


class EntrarDoCodex(_Entrar):
    def test_exec_roda_o_binario_fixado_com_o_config_imposto_e_a_saida_volta_para_pasta_nova(self):
        self.escreve = {"resultado.md": b"pronto"}
        r = self.entrar(prompt="resuma o contrato sigiloso")
        self.assertTrue(r["ok"], r)
        comando = self.comando()
        self.assertEqual(comando[comando.index(J.SH_DO_PROMPT) + 1], f"{self.cfg.programas}/codex/0.166.0/codex")
        self.assertNotIn("sigiloso", " ".join(self.rodadas[0]))                      # o prompt nunca está no argv
        partes = self.memfds["jaula-args"].split(b"\0")
        self.assertEqual(partes[:2], [b"--setenv", b"FUNDACAO_PROMPT"])                  # ...e sim no descritor
        self.assertTrue(partes[2].decode("utf-8").endswith("resuma o contrato sigiloso"))
        self.assertIn('approval_policy = "never"', self.visto["config"])
        self.assertIn('sandbox_mode = "workspace-write"', self.visto["config"])
        self.assertEqual(self.visto["projeto"], ["notas/a.md"])                          # só o que o pedido listou
        self.assertEqual(r["stdout"], "resposta do Codex")
        self.assertIn("dado de terceiro", r["aviso"])
        destino = self.projeto / "outputs" / "codex" / "pedido-cdx-0001"
        self.assertEqual([p.name for p in destino.iterdir()], ["resultado.md"])
        self.assertFalse((self.estado_p / "trabalho" / "pedido-cdx-0001").exists())
        self.assertTrue((self.home / "auth.json").is_file())                             # a credencial fica no estado privado

    def test_n_cdx_4_e_8_instrucao_config_de_projeto_e_segredo_nao_chegam_ao_codex(self):
        r = self.entrar(arquivos=["notas/a.md", "AGENTS.md", ".codex/config.toml", ".env"])
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.visto["projeto"], ["notas/a.md"])
        self.assertEqual(sorted(i["caminho"] for i in r["ida"]["ignorados"]), [".codex/config.toml", ".env", "AGENTS.md"])
        self.assertIn("project_doc_max_bytes = 0", self.visto["config"])                 # e o AGENTS.md nem vale como instrução

    def test_n_cdx_6_titular_leva_o_projeto_e_a_ligacao_para_o_codex_home_nao_e_seguida(self):
        try:
            (self.projeto / "atalho").symlink_to(self.home, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"link simbólico indisponível neste ambiente: {exc}")
        with mock.patch.dict(os.environ, {"TERM": "vt100"}):
            r = self.entrar("codex-titular")
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.visto["projeto"], ["notas/a.md", "outputs/velho.txt"])    # sem AGENTS.md, .codex/, .env nem atalho/
        self.assertIn("atalho", [i["caminho"] for i in r["ida"]["ignorados"]])
        self.assertNotIn("auth.json", " ".join(self.visto["projeto"]))
        self.assertIn('approval_policy = "on-request"', self.visto["config"])
        self.assertIn(["--setenv", "TERM", "vt100"], [self.rodadas[0][i:i + 3] for i in range(len(self.rodadas[0]) - 2)])
        self.assertNotIn("jaula-args", self.memfds)                                      # o terminal não leva segredo nenhum
        self.assertEqual(self.comando()[-3:], ["--no-daemon", "-C", "/trabalho/saida"])

    def test_sem_login_nada_roda_e_a_mensagem_manda_o_titular_fazer_o_login(self):
        (self.home / "auth.json").unlink()
        for modo in ("codex-exec", "codex-titular"):
            with self.subTest(modo=modo), self.assertRaises(J.Recusa) as r:
                self.entrar(modo)
            self.assertIn("abrir-codex-criador --login", str(r.exception))
            self.assertIn("nunca da sessão", str(r.exception))
        self.nada_rodou()

    def test_n_cdx_5_r55_ausente_futuro_ou_velho_demais_recusa_a_cada_uso(self):
        for nome, r55 in (("ausente", None), ("desligado falso", {**R55, "treinamento_desligado": False}),
                          ("futuro", {**R55, "conferido_em": "2026-11-09"}), ("velho", {**R55, "conferido_em": "2026-08-01"}),
                          ("ilegível", {**R55, "conferido_em": "ontem"})):
            item = {k: v for k, v in ITEM.items() if k != "r55"}
            self.ficha["outras_llm"] = [item if r55 is None else {**item, "r55": r55}]
            for modo in ("codex-exec", "codex-titular"):
                with self.subTest(r55=nome, modo=modo), self.assertRaises(J.Recusa) as e:
                    self.entrar(modo)
                self.assertIn("R55", str(e.exception))
        self.nada_rodou()
        self.ficha["outras_llm"] = [{**ITEM, "r55": {**R55, "conferido_em": "2026-08-10"}}]        # 90 dias: ainda vale
        self.assertTrue(self.entrar()["ok"])

    def test_n_cdx_1_sem_a_secao_ou_sem_o_modo_na_ficha_e_sem_o_canario_aprovado_o_modo_nao_abre(self):
        casos = [("sem outras_llm", {"valida": True, "project_id": "criador"}, "codex-exec", "outras_llm"),
                 ("só o titular", {**FICHA, "outras_llm": [{**ITEM, "modos": ["titular"]}]}, "codex-exec", "não abre"),
                 ("só o exec", {**FICHA, "outras_llm": [{**ITEM, "modos": ["exec"]}]}, "codex-titular", "não abre"),
                 ("outro provedor", {**FICHA, "outras_llm": [{**ITEM, "provedor": "outro"}]}, "codex-exec", "não abre"),
                 ("autenticação inventada", {**FICHA, "outras_llm": [{**ITEM, "autenticacao": "chave"}]}, "codex-exec", "autenticacao")]
        for nome, ficha, modo, trecho in casos:
            self.ficha = ficha
            with self.subTest(nome), self.assertRaises(J.Recusa) as e:
                self.entrar(modo)
            self.assertIn(trecho, str(e.exception))
        self.ficha = json.loads(json.dumps(FICHA))
        for nome, relatorio in (("sem relatório", None), ("reprovado", {**RELATORIO, "modos": {"codex-exec": {"aprovado": False}}}),
                                ("de outra versão", {**RELATORIO, "hashes": {**HASHES, "bwrap": "d" * 64}})):
            self.relatorio = relatorio
            with self.subTest(nome), self.assertRaises(J.Recusa):
                self.entrar()
        self.nada_rodou()

    def test_n_cdx_7_token_literal_na_saida_ou_na_resposta_nao_volta_para_o_projeto_nem_para_a_sessao(self):
        self.escreve = {"vazou.txt": f"x {TOKEN} y".encode(), "renovacao.txt": ("a" + RENOVA).encode(), "ok.txt": b"ok"}
        self.stdout = f"o token é {TOKEN}".encode()
        r = self.entrar()
        self.assertEqual(sorted(c["arquivo"] for c in r["saida"]["copiados"]), ["ok.txt"])
        self.assertEqual(sorted(c["arquivo"] for c in r["saida"]["recusados"]), ["renovacao.txt", "vazou.txt"])
        self.assertEqual((r["stdout"], r["stderr"]), (J.RETIDO, ""))
        destino = self.projeto / "outputs" / "codex" / "pedido-cdx-0001"
        self.assertEqual([p.name for p in destino.iterdir()], ["ok.txt"])
        self.assertNotIn(TOKEN, json.dumps(r))
        self.assertNotIn("account", json.dumps(r["saida"]))                              # nem o motivo cita o trecho
        self.stdout = b"renovado em 2026-11-08T10:00:00.123456789Z"                       # a data de renovação não é segredo
        self.rodadas.clear()
        outro = J.entrar(self.cfg, "criador", "codex-exec", pedido(id="pedido-cdx-0002", prompt="p", arquivos=["notas/a.md"]),
                         raiz=str(self.raiz), ficha=self.ficha, relatorio=self.relatorio, hoje=HOJE, hashes_atuais=HASHES)
        self.assertIn("renovado em", outro["stdout"])

    def test_auth_json_ilegivel_ou_com_modo_aberto_segura_a_resposta_e_a_saida(self):
        (self.home / "auth.json").write_text("isto não é JSON", encoding="utf-8")
        with self.assertRaises(J.Recusa):                                                # antes de rodar: nem a conta se confere
            self.entrar()
        self.nada_rodou()
        if not hasattr(os, "geteuid"):
            self.skipTest("o modo 0600 do auth.json só existe no Linux")
        self.escrever_auth()
        os.chmod(self.home / "auth.json", 0o644)
        with self.assertRaises(J.Recusa) as e:
            self.entrar()
        self.assertIn("0600", str(e.exception))

    def test_a_medida_do_root_troca_o_sandbox_e_a_ficha_ou_o_pedido_nao(self):
        self.entrar()
        self.assertIn('sandbox_mode = "workspace-write"', self.visto["config"])
        self.relatorio["modos"]["codex-exec"]["medidas"] = {"sandbox_codex": "danger-full-access"}
        self.ficha["outras_llm"][0]["sandbox_codex"] = "danger-full-access"             # campo livre da ficha: nunca é lido
        self.entrar()
        self.assertIn('sandbox_mode = "danger-full-access"', self.visto["config"])
        self.assertIn('network_access = false', self.visto["config"])
        self.relatorio["modos"]["codex-exec"]["medidas"] = {}
        with self.assertRaises(J.Recusa):
            self.entrar(sandbox_codex="danger-full-access")                               # nem o pedido
        self.entrar(id="pedido-cdx-0003")
        self.assertIn('sandbox_mode = "workspace-write"', self.visto["config"])

    def test_f1_o_codex_da_sessao_com_a_conta_do_chatgpt_e_recusado_e_o_do_titular_segue(self):
        """Prova negativa da F1 na entrada fixa (a defesa a mais; o preparo ja nem abre a operacao nem a linha da sudoers): o
        `codex-exec` e o canario dele recusam com `conta_chatgpt`, sem rodar nada e sem tocar no CODEX_HOME."""
        self.ficha = json.loads(json.dumps(FICHA_CONTA))
        with self.assertRaises(J.Recusa) as e:
            self.entrar()
        self.assertEqual(str(e.exception), J.MOTIVO_CODEX_EXEC_COM_CONTA)
        for trecho in ("chave de API do projeto, com teto de gasto", "abrir-codex-<projeto>", "CODEX_HOME"):
            self.assertIn(trecho, str(e.exception))
        with self.assertRaises(J.Recusa) as e:
            J.entrar(self.cfg, "criador", "canario", pedido(como="codex-exec", dominios=["chatgpt.com"]), raiz=str(self.raiz),
                     ficha=self.ficha, relatorio=self.relatorio, hoje=HOJE, hashes_atuais=HASHES)
        self.assertEqual(str(e.exception), J.MOTIVO_CODEX_EXEC_COM_CONTA)
        self.nada_rodou()
        self.assertTrue((self.home / "auth.json").is_file())
        with mock.patch.dict(os.environ, {"TERM": "vt100"}):                            # a janela do titular segue com a conta
            self.assertTrue(self.entrar("codex-titular")["ok"])
        self.assertFalse(J.codex_exec_aberto_pela_ficha(FICHA_CONTA))
        self.assertTrue(J.codex_exec_aberto_pela_ficha(FICHA))
        for lixo in (None, {}, {"outras_llm": []}, {"outras_llm": [3]}, {"outras_llm": [{"autenticacao": "chave"}]}):
            self.assertFalse(J.codex_exec_aberto_pela_ficha(lixo), lixo)

    def test_login_entra_na_conta_sem_projeto_sem_saida_e_so_com_a_conta_do_chatgpt(self):
        self.ficha = json.loads(json.dumps(FICHA_CONTA))
        (self.home / "auth.json").unlink()                                              # ainda não há conta: é o que o login cria
        r = self.entrar("codex-titular", acao="login")
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.comando()[-2:], ["login", "--device-auth"])
        self.assertNotIn("/trabalho/projeto", self.rodadas[0])
        self.assertNotIn("projeto", self.visto)
        self.assertNotIn("saida", r)                                                     # nada volta para o projeto
        self.assertFalse((self.projeto / "outputs" / "codex").exists())
        self.ficha["outras_llm"][0]["autenticacao"] = "chave_api"
        with self.assertRaises(J.Recusa) as e:
            self.entrar("codex-titular", acao="login")
        self.assertIn("só da conta do ChatGPT", str(e.exception))
        self.ficha = json.loads(json.dumps(FICHA))
        self.relatorio = None                                                             # sem canário aprovado, nem o login abre
        with self.assertRaises(J.Recusa):
            self.entrar("codex-titular", acao="login")

    def test_config_do_estado_que_e_ligacao_ou_a_montagem_que_falta_nao_rodam(self):
        try:
            (self.home / "config.toml").symlink_to(self.base / "alvo")
        except OSError as exc:
            self.skipTest(f"link simbólico indisponível neste ambiente: {exc}")
        with self.assertRaises(J.Recusa):
            self.entrar()
        (self.home / "config.toml").unlink()
        with mock.patch.object(J, "montar_argv", return_value=["/usr/bin/bwrap", "--", "/x"]):
            with self.assertRaises(J.Recusa) as e:
                self.entrar()
        self.assertIn("config.toml imposto", str(e.exception))
        self.assertEqual(self.rodadas, [])
        self.assertFalse((self.estado_p / "trabalho" / "pedido-cdx-0001").exists())      # a pasta de trabalho some mesmo assim


class SaidaRetidaDoTitular(_Entrar):
    """F10 (3ª passada da revisão de segurança da 1.7.11): a saída da janela do Codex do titular fica retida no estado da jaula e
    só vai ao projeto depois de o titular confirmar a lista (`listar` e `trazer`). Prova negativa: sem confirmação, nada chega ao
    projeto; com ela, só a lista confirmada chega."""

    def setUp(self):
        super().setUp()
        self.escreve = {"resultado.md": b"pronto", "sub/b.txt": b"bb"}
        self.destino_pai = self.projeto / "outputs" / "codex"

    def tui(self):
        with mock.patch.dict(os.environ, {"TERM": "vt100"}):
            return self.entrar("codex-titular")

    def retida_de(self, ident):
        return self.estado_p / "codex" / J.PASTA_RETIDA / ident

    def pedir(self, acao, ident, **campos):
        return self.entrar("codex-titular", acao=acao, retida=ident, id=f"pedido-{acao}-0001", **campos)

    def test_sem_confirmacao_nada_chega_ao_projeto_e_a_saida_fica_retida_com_a_lista(self):
        r = self.tui()
        self.assertTrue(r["ok"], r)
        self.assertFalse(self.destino_pai.exists())                                     # nada voltou ao projeto
        s = r["saida"]
        self.assertFalse(s["voltou"])
        self.assertEqual(sorted((c["arquivo"], c["bytes"]) for c in s["pendente"]), [("resultado.md", 6), ("sub/b.txt", 2)])
        self.assertEqual(s["destino"], f"outputs/codex/{s['retida']}")
        self.assertEqual(s["lista_sha256"], J.lista_sha256(s["pendente"]))
        retida = self.retida_de(s["retida"])
        self.assertEqual(sorted(p.relative_to(retida).as_posix() for p in retida.rglob("*") if p.is_file()),
                         ["resultado.md", "sub/b.txt"])
        self.assertTrue((self.estado_p / "codex" / J.PASTA_RETIDA / f"{s['retida']}.json").is_file())
        self.assertTrue(s["onde"].endswith(f"/codex/{J.PASTA_RETIDA}/{s['retida']}"), s["onde"])
        self.assertFalse((self.estado_p / "trabalho" / s["retida"]).exists())            # a pasta de trabalho some como sempre
        listada = self.pedir("listar", s["retida"])                                      # listar também não grava no projeto
        self.assertTrue(listada["ok"], listada)
        self.assertEqual((listada["saida"]["pendente"], listada["saida"]["lista_sha256"]), (s["pendente"], s["lista_sha256"]))
        self.assertFalse(self.destino_pai.exists())

    def test_o_segredo_e_o_que_a_jaula_recusa_nao_entram_na_retida_nem_na_lista(self):
        self.escreve = {"ok.txt": b"ok", "vazou.txt": f"x {TOKEN} y".encode()}
        s = self.tui()["saida"]
        self.assertEqual([c["arquivo"] for c in s["pendente"]], ["ok.txt"])
        self.assertEqual([c["arquivo"] for c in s["recusados"]], ["vazou.txt"])
        self.assertFalse((self.retida_de(s["retida"]) / "vazou.txt").exists())
        self.assertNotIn(TOKEN, json.dumps(s))

    def test_saida_vazia_ou_toda_recusada_nao_guarda_nada(self):
        self.escreve = {}
        s = self.tui()["saida"]
        self.assertEqual((s["pendente"], s["onde"]), ([], None))
        self.assertFalse(self.retida_de(s["retida"]).exists())
        self.assertFalse((self.estado_p / "codex" / J.PASTA_RETIDA / f"{s['retida']}.json").exists())
        with self.assertRaises(J.Recusa):
            self.pedir("listar", s["retida"])

    def test_com_a_confirmacao_so_a_lista_mostrada_chega_e_a_retida_some(self):
        s = self.tui()["saida"]
        ident, retida = s["retida"], self.retida_de(s["retida"])
        extra = retida / "plantado.txt"                                                  # algo que a lista não tem
        extra.write_bytes(b"fora da lista")
        r = self.pedir("trazer", ident, lista_sha256=s["lista_sha256"])
        self.assertFalse(r["ok"], r)                                                     # veio tudo da lista, mas sobrou o plantado
        destino = self.destino_pai / ident
        self.assertEqual(sorted(p.relative_to(destino).as_posix() for p in destino.rglob("*") if p.is_file()),
                         ["resultado.md", "sub/b.txt"])
        self.assertEqual(sorted((c["arquivo"], c["sha256"]) for c in r["saida"]["copiados"]),
                         sorted((c["arquivo"], c["sha256"]) for c in s["pendente"]))
        self.assertEqual([c["arquivo"] for c in r["saida"]["recusados"]], ["plantado.txt"])
        self.assertFalse((destino / "plantado.txt").exists())
        self.assertTrue(retida.exists())                                                 # não chegou tudo limpo: a retida fica
        extra.unlink()

    def test_trazer_limpo_copia_a_lista_confere_o_conteudo_e_apaga_a_retida(self):
        s = self.tui()["saida"]
        ident = s["retida"]
        r = self.pedir("trazer", ident, lista_sha256=s["lista_sha256"])
        self.assertTrue(r["ok"], r)
        destino = self.destino_pai / ident
        self.assertEqual((destino / "resultado.md").read_bytes(), b"pronto")
        self.assertEqual((destino / "sub" / "b.txt").read_bytes(), b"bb")
        self.assertEqual(sorted(c["arquivo"] for c in r["saida"]["copiados"]), ["resultado.md", "sub/b.txt"])
        self.assertEqual((r["saida"]["voltou"], r["saida"]["retida"], r["saida"]["recusados_total"]), (True, None, 0))
        self.assertFalse(self.retida_de(ident).exists())
        self.assertFalse((self.estado_p / "codex" / J.PASTA_RETIDA / f"{ident}.json").exists())
        with self.assertRaises(J.Recusa):                                                # e não se traz duas vezes
            self.pedir("trazer", ident, lista_sha256=s["lista_sha256"])

    def test_lista_que_nao_e_a_confirmada_recusa_e_nada_chega(self):
        s = self.tui()["saida"]
        for ruim in ("0" * 64, J.lista_sha256(s["pendente"][:1])):
            with self.subTest(ruim[:8]), self.assertRaises(J.Recusa) as e:
                self.pedir("trazer", s["retida"], lista_sha256=ruim)
            self.assertIn("não é a que você confirmou", str(e.exception))
        self.assertFalse(self.destino_pai.exists())
        self.assertTrue(self.retida_de(s["retida"]).exists())

    def test_arquivo_trocado_na_retida_depois_da_lista_nao_chega(self):
        s = self.tui()["saida"]
        (self.retida_de(s["retida"]) / "resultado.md").write_bytes(b"TROCADO")
        r = self.pedir("trazer", s["retida"], lista_sha256=s["lista_sha256"])
        self.assertFalse(r["ok"], r)
        destino = self.destino_pai / s["retida"]
        self.assertFalse((destino / "resultado.md").exists())                            # o SHA-256 da lista não bate
        self.assertEqual([c["arquivo"] for c in r["saida"]["copiados"]], ["sub/b.txt"])
        self.assertIn("resultado.md", [c["arquivo"] for c in r["saida"]["recusados"]])
        self.assertEqual(list(destino.glob(".copiando-*")), [])                          # sem sobra de temporário

    def test_retida_que_nao_existe_ou_com_lista_adulterada_recusa(self):
        with self.assertRaises(J.Recusa) as e:
            self.pedir("listar", "t-20261109-ffffff")
        self.assertIn("não há saída retida", str(e.exception))
        s = self.tui()["saida"]
        manifesto = self.estado_p / "codex" / J.PASTA_RETIDA / f"{s['retida']}.json"
        for nome, dados in (("fora do esquema", {"schema_version": "x", "id": s["retida"], "copiados": s["pendente"]}),
                            ("id de outro", {"schema_version": J.ESQUEMA_RETIDA, "id": "t-20261109-ffffff", "copiados": s["pendente"]}),
                            ("sha inválido", {"schema_version": J.ESQUEMA_RETIDA, "id": s["retida"],
                                              "copiados": [{"arquivo": "a", "sha256": "z", "bytes": 1}]}),
                            ("vazia", {"schema_version": J.ESQUEMA_RETIDA, "id": s["retida"], "copiados": []})):
            manifesto.write_text(json.dumps(dados), encoding="utf-8")
            with self.subTest(nome), self.assertRaises(J.Recusa):
                self.pedir("listar", s["retida"])
        self.assertFalse(self.destino_pai.exists())

    def test_listar_e_trazer_seguem_a_ficha_e_nao_rodam_nada_na_caixa(self):
        s = self.tui()["saida"]
        self.rodadas.clear()
        self.pedir("listar", s["retida"])
        self.pedir("trazer", s["retida"], lista_sha256=s["lista_sha256"])
        self.assertEqual(self.rodadas, [])                                               # nem bwrap nem pty
        s2 = self.tui()["saida"]
        self.ficha = {**FICHA, "outras_llm": [{**ITEM, "modos": ["exec"]}]}               # a ficha deixou de abrir a janela do titular
        with self.assertRaises(J.Recusa):
            self.pedir("trazer", s2["retida"], lista_sha256=s2["lista_sha256"])
        self.assertFalse((self.destino_pai / s2["retida"]).exists())

    def test_destino_que_ja_existe_recusa_e_a_retida_fica(self):
        s = self.tui()["saida"]
        (self.destino_pai / s["retida"]).mkdir(parents=True)
        with self.assertRaises(J.Recusa):
            self.pedir("trazer", s["retida"], lista_sha256=s["lista_sha256"])
        self.assertTrue(self.retida_de(s["retida"]).exists())

    def test_o_login_e_o_exec_nao_mudam(self):
        self.ficha = json.loads(json.dumps(FICHA_CONTA))
        (self.home / "auth.json").unlink()
        self.assertNotIn("saida", self.entrar("codex-titular", acao="login"))
        self.escrever_auth()
        self.ficha = json.loads(json.dumps(FICHA))
        self.escreve = {"resultado.md": b"pronto"}
        r = self.entrar()                                                                # o exec da sessão: a volta segue direta
        self.assertTrue((self.destino_pai / "pedido-cdx-0001" / "resultado.md").is_file())
        self.assertNotIn("retida", r["saida"])


class SegredosDoCodex(unittest.TestCase):
    def setUp(self):
        self.pasta = Path(tempfile.mkdtemp(prefix="auth-cdx-1711-")).resolve()
        self.addCleanup(shutil.rmtree, self.pasta, True)

    def gravar(self, dados, modo=0o600):
        (self.pasta / "auth.json").write_text(dados if isinstance(dados, str) else json.dumps(dados), encoding="utf-8")
        os.chmod(self.pasta / "auth.json", modo)

    def test_sem_arquivo_e_none_com_arquivo_sao_os_valores_longos_menos_a_data_de_renovacao(self):
        self.assertIsNone(J.segredos_do_codex(str(self.pasta)))
        self.gravar({"OPENAI_API_KEY": None, "tokens": {"id_token": TOKEN, "refresh_token": [RENOVA], "account_id": "curto"},
                     "last_refresh": "2026-11-08T10:00:00Z"})
        self.assertEqual(sorted(J.segredos_do_codex(str(self.pasta))), sorted([TOKEN, RENOVA]))
        self.gravar({"OPENAI_API_KEY": "-".join(("chave", "ficticia", "0123456789", "ABCDEFG"))})
        self.assertEqual(len(J.segredos_do_codex(str(self.pasta))), 1)

    def test_arquivo_estranho_recusa_e_a_saida_nao_volta(self):
        for ruim in ("não é json", '{"a": NaN}', '{"a": 1, "a": 2}', "[" * 5000, "x" * (2 << 20)):
            self.gravar(ruim)
            with self.subTest(ruim[:12]), self.assertRaises(J.Recusa):
                J.segredos_do_codex(str(self.pasta))
        if hasattr(os, "geteuid"):
            self.gravar({"a": TOKEN}, 0o640)
            with self.assertRaises(J.Recusa):
                J.segredos_do_codex(str(self.pasta))

    def test_segredos_da_jaula_do_codex_vem_do_estado_do_modo_e_o_canario_nao_tem_estado(self):
        (self.pasta / "codex" / "home").mkdir(parents=True)
        (self.pasta / "codex" / "home" / "auth.json").write_text(json.dumps({"t": TOKEN}), encoding="utf-8")
        os.chmod(self.pasta / "codex" / "home" / "auth.json", 0o600)
        self.assertEqual(J.segredos_da_jaula(str(self.pasta), J.perfil_do_modo("codex-exec")), [TOKEN])
        self.assertEqual(J.segredos_da_jaula(str(self.pasta), J.perfil_do_modo("canario", None, "codex-exec")), [])
        self.assertEqual(J.segredos_da_jaula(str(self.pasta), J.perfil_do_modo("codex-titular", None, None, "login")), [TOKEN])


BINARIO = b"binario falso do codex\n"
MEMBRO = "codex-x86_64-unknown-linux-musl"


class PreparoDoCodex(unittest.TestCase):
    """O download (arquivo falso, nunca rede), o SHA-256 conferido antes de instalar e o que o ensaio nunca faz."""

    @classmethod
    def setUpClass(cls):
        cls.m = carregar_preparo()
        cls.pj = cls.m.preparo_jaula()

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="preparo-cdx-1711-")).resolve()
        self.addCleanup(shutil.rmtree, self.base, True)
        (self.base / "jaula-ensaio").mkdir()
        self.caminhos = self.pj.caminhos_de_ensaio(self.base / "jaula-ensaio", self.base / "area")
        self.chamadas = []
        self.pasta = Path(self.caminhos.programas) / "codex" / "0.166.0"

    def tgz(self, *membros) -> bytes:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for nome, dados, tipo in membros:
                info = tarfile.TarInfo(nome)
                info.type, info.size = tipo, (len(dados) if tipo == tarfile.REGTYPE else 0)
                if tipo == tarfile.SYMTYPE:
                    info.linkname = "/etc/passwd"
                tar.addfile(info, io.BytesIO(dados) if tipo == tarfile.REGTYPE else None)
        return buf.getvalue()

    def bom(self) -> bytes:
        return self.tgz((MEMBRO, BINARIO, tarfile.REGTYPE))

    @contextlib.contextmanager
    def fixando(self, dados: bytes):
        """O pino da skill trocado pelo do arquivo falso (tamanho e SHA-256 dele): o que a API do GitHub publicaria."""
        pins = {**self.pj.pins_do_codex(), "tamanho": len(dados), "sha256": hashlib.sha256(dados).hexdigest()}
        with mock.patch.object(self.pj, "pins_do_codex", return_value=pins):
            yield pins

    def fixar(self, dados: bytes) -> dict:
        contexto = self.fixando(dados)
        pins = contexto.__enter__()
        self.addCleanup(contexto.__exit__, None, None, None)
        return pins

    def baixar_de(self, dados: bytes):
        def baixar(url, destino, limite):
            self.chamadas.append((url, limite))
            Path(destino).write_bytes(dados)
        return baixar

    def instalar(self, baixar, **kw):
        return self.pj.instalar_codex_jaula(SKILL, self.caminhos, {"necessaria": True, "codex": True}, baixar=baixar, **kw)

    def nada_instalado(self):
        self.assertFalse((self.pasta / "codex").exists())
        self.assertFalse(list((Path(self.caminhos.programas) / "codex").glob(".baixando-*")))

    def test_instala_so_depois_de_conferir_tamanho_e_sha256_e_registra_o_binario(self):
        dados = self.bom()
        pins = self.fixar(dados)
        res = self.instalar(self.baixar_de(dados))
        self.assertEqual(self.chamadas, [(f"https://github.com/openai/codex/releases/download/rust-v0.166.0/{pins['arquivo']}",
                                          len(dados))])                                    # o limite do download é o tamanho fixado
        self.assertEqual((self.pasta / "codex").read_bytes(), BINARIO)
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE((self.pasta / "codex").stat().st_mode), 0o755)
        registro = json.loads((self.pasta / "instalado.json").read_text(encoding="utf-8"))
        self.assertEqual((registro["sha256_arquivo"], registro["sha256_binario"], registro["bytes_binario"]),
                         (pins["sha256"], hashlib.sha256(BINARIO).hexdigest(), len(BINARIO)))
        self.assertEqual([a["acao"] for a in res["acoes"]], ["criar", "criar"])
        self.assertFalse(list((self.pasta.parent).glob(".baixando-*")))                  # nada de rascunho sobrando
        antes = len(self.chamadas)
        self.assertEqual([a["acao"] for a in self.instalar(self.baixar_de(dados))["acoes"]], ["igual"])
        self.assertEqual(len(self.chamadas), antes)                                        # a 2ª vez não baixa
        (self.pasta / "codex").write_bytes(b"adulterado")                                  # binário que difere do registro: refaz
        self.assertEqual(self.instalar(self.baixar_de(dados))["acoes"][0]["acao"], "atualizar")
        self.assertEqual((self.pasta / "codex").read_bytes(), BINARIO)

    def test_sha256_ou_tamanho_diferente_do_pino_nao_instala_nada(self):
        dados = self.bom()
        self.fixar(dados)
        outro = dados[:-1] + bytes([dados[-1] ^ 1])                                        # mesmo tamanho, outro conteúdo
        for nome, baixado in (("sha256", outro), ("tamanho", dados + b"x"), ("vazio", b"")):
            with self.subTest(nome), self.assertRaises(self.m.EntradaInvalida) as e:
                self.instalar(self.baixar_de(baixado))
            self.assertIn("NÃO confere", str(e.exception))
            self.assertIn("nada foi instalado", str(e.exception))
            self.nada_instalado()
        self.assertFalse((self.pasta / "instalado.json").exists())

    def test_o_tar_gz_so_pode_ter_o_membro_esperado_como_arquivo_comum(self):
        regular = tarfile.REGTYPE
        for nome, dados in (("dois membros", self.tgz((MEMBRO, BINARIO, regular), ("outro", b"x", regular))),
                            ("nome trocado", self.tgz(("codex", BINARIO, regular))),
                            ("caminho com ..", self.tgz((f"../{MEMBRO}", BINARIO, regular))),
                            ("ligação", self.tgz((MEMBRO, b"", tarfile.SYMTYPE))),
                            ("pasta", self.tgz((MEMBRO, b"", tarfile.DIRTYPE))), ("vazio", self.tgz())):
            with self.subTest(nome), self.fixando(dados), self.assertRaises(self.m.EntradaInvalida) as e:   # o SHA-256 bate
                self.instalar(self.baixar_de(dados))
            self.assertIn("nada foi instalado", str(e.exception))
            self.nada_instalado()

    def test_so_com_a_secao_ou_preparar_o_ensaio_nunca_baixa_e_fora_do_ensaio_exige_root(self):
        self.assertEqual(self.pj.instalar_codex_jaula(SKILL, self.caminhos, {"necessaria": True, "codex": False}),
                         {"acoes": [], "necessaria": False})
        simulado = self.pj.instalar_codex_jaula(SKILL, self.caminhos, {"necessaria": True, "codex": True}, simular=True)
        self.assertFalse((Path(self.caminhos.programas) / "codex").exists())
        texto = "\n".join(self.pj.texto_do_codex(simulado))
        pins = J.pins_do_codex()
        for trecho in ("nada foi baixado", "https://github.com/openai/codex/releases/download/rust-v0.166.0/"
                       "codex-x86_64-unknown-linux-musl.tar.gz", "121.764.138 bytes", pins["sha256"], "ANTES de instalar", "sigstore"):
            self.assertIn(trecho, texto)
        with self.assertRaises(self.m.EntradaInvalida) as e:                                # ensaio sem comando falso: não baixa
            self.pj.instalar_codex_jaula(SKILL, self.caminhos, {"necessaria": True, "codex": True})
        self.assertIn("nunca baixa", str(e.exception))
        with self.assertRaises(self.m.EntradaInvalida) as e:                                # sem ensaio e sem root
            self.pj.instalar_codex_jaula(SKILL, self.pj.Caminhos(**{**self.caminhos._asdict(), "ensaio": False}),
                                         {"necessaria": True, "codex": True}, baixar=lambda *a: None)
        self.assertIn("dono root", str(e.exception))
        self.assertIn("nada a instalar", "\n".join(self.pj.texto_do_codex({"necessaria": False})))

    def test_o_download_so_aceita_o_release_fixado_em_https(self):
        for url in ("https://exemplo.org/codex.tar.gz", "http://github.com/openai/codex/releases/download/rust-v0.166.0/x",
                    "https://github.com/outro/repo/releases/download/rust-v0.166.0/x",
                    "https://github.com.exemplo.org/openai/codex/releases/download/x"):
            with self.subTest(url), self.assertRaises(self.m.EntradaInvalida):
                self.pj.baixar_https(url, self.base / "x.bin", 10)
        self.assertFalse((self.base / "x.bin").exists())

    def test_pino_da_skill_fora_da_forma_nao_serve_de_fonte_do_download(self):
        with tempfile.TemporaryDirectory() as d:
            destino = Path(d) / "assets" / "host" / "wsl" / J.PINS_DO_CODEX
            destino.parent.mkdir(parents=True)
            destino.write_text(json.dumps({**J.pins_do_codex(), "sha256": "zz"}), encoding="utf-8")
            with self.assertRaises(self.m.EntradaInvalida):
                self.pj.pins_do_codex(d)

    def test_a_linha_de_comando_planeja_sem_baixar_e_o_ensaio_real_recusa(self):
        ab = ficha_aplicada(self.m, outras_llm=secao_codex())
        gravar_area(self.base, self.m, ab, self.caminhos)
        base = [sys.executable, "-I", "-B", str(SKILL / "assets" / "host" / "preparo_host.py"), "instalar-codex-jaula", "--raiz",
                "/mnt/e/Raiz Exemplo", "--projeto", "caso-real", "--usuario", USUARIO_DO_ENSAIO, "--area-raiz",
                str(self.base / "area"), "--ensaio-base", str(self.base / "jaula-ensaio")]
        r = subprocess.run([*base, "--simular", "--texto"], capture_output=True, text=True, encoding="utf-8", env=ENV, timeout=120,
                           stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("rust-v0.166.0", r.stdout)
        self.assertFalse((Path(self.caminhos.programas) / "codex").exists())
        r = subprocess.run([*base, "--texto"], capture_output=True, text=True, encoding="utf-8", env=ENV, timeout=120,
                           stdin=subprocess.DEVNULL)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("nunca baixa", r.stdout + r.stderr)

    def test_o_passo_6c_do_preparar_wsl_so_chama_o_ajudante_mostra_o_plano_antes_e_o_ensaio_nunca_baixa(self):
        texto = (WSL / "preparar-wsl.sh").read_text(encoding="utf-8")
        passo = texto[texto.index("# 6c. O Codex da jaula"):texto.index("if [ ${#CANARIOS_JAULA[@]} -gt 0 ]; then\n          saida=$(chama_jaula instalar-canario-jaula")]
        codigo = " ".join(l.strip() for l in passo.splitlines() if not l.lstrip().startswith("#"))
        for baixa in ("apt-get", "pip ", "curl", "wget", "tar -x", "sha256sum", "npm ", "git clone"):
            self.assertNotIn(baixa, codigo)                                                 # o shell não baixa nem confere hash
        self.assertIn('instalar-codex-jaula "${args_jaula[@]}" --simular --texto', codigo)    # o plano vem antes
        self.assertLess(codigo.index("--simular"), codigo.index("chama_jaula instalar-codex-jaula"))
        self.assertIn('elif [ "$ENSAIO" = 1 ]', codigo)
        self.assertIn("nada é baixado", codigo)
        self.assertEqual(len([l for l in texto.splitlines() if "sudo" in l and "$AJUDANTE" in l and not l.lstrip().startswith("#")]), 3)


class LancadorEPlanoDoCodex(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = carregar_preparo()
        cls.pj = cls.m.preparo_jaula()

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="lancador-cdx-1711-")).resolve()
        self.addCleanup(shutil.rmtree, self.base, True)
        (self.base / "jaula-ensaio").mkdir()
        self.caminhos = self.pj.caminhos_de_ensaio(self.base / "jaula-ensaio", self.base / "area")
        Path(self.caminhos.bwrap).write_bytes(b"bwrap de ensaio\n")

    def lancador(self, projeto="criador"):
        texto = self.pj.texto_do_lancador_codex(projeto, "/usr/local/lib/fundacao-ia/jaula/1.7.11")
        ns = {"__name__": "lancador"}
        exec(compile(texto, "abrir-codex", "exec"), ns)
        return texto, ns

    def executar(self, ns, argv, codigo=0, resposta=None, euid=1000):
        chamadas = []

        def run(args, **kw):
            chamadas.append((list(args), kw))
            return types.SimpleNamespace(returncode=codigo, stdout=json.dumps(resposta or {"ok": codigo == 0}).encode())
        ns["subprocess"] = types.SimpleNamespace(run=run, PIPE=-1)
        ns["os"] = types.SimpleNamespace(environ={"TERM": "xterm"}, geteuid=lambda: euid)
        with contextlib.redirect_stdout(io.StringIO()) as saida, contextlib.redirect_stderr(io.StringIO()) as erro:
            rc = ns["main"](argv)
        return rc, chamadas, saida.getvalue(), erro.getvalue()

    def test_o_lancador_tem_so_valores_fixos_e_o_rotulo_do_risco_da_conta(self):
        texto, ns = self.lancador()
        self.assertNotIn("{{", texto)
        self.assertIn(self.pj.MARCA_DO_LANCADOR_CODEX, texto)
        self.assertEqual((ns["PROJETO"], ns["USUARIO_DA_JAULA"], ns["ENTRADA"]),
                         ("criador", "fundacao-jaula", "/usr/local/lib/fundacao-ia/jaula/1.7.11/jaula-entrar"))
        self.assertEqual(ns["ROTULO"], J.ROTULO_DO_CODEX_CONTA)
        for risco in ("conta INTEIRA", "saída para qualquer destino", "OpenAI", "0600", "90 dias"):
            self.assertIn(risco, ns["ROTULO"])

    def test_o_pedido_do_lancador_e_fechado_e_a_entrada_fixa_o_aceita(self):
        _, ns = self.lancador()
        self.assertIsNone(ns["montar_pedido"]([]))                                          # o terminal: pedido padrão
        p = ns["montar_pedido"](["--login"])
        self.assertEqual(set(p), {"schema_version", "id", "acao"})
        self.assertEqual(J.validar_pedido(json.dumps(p).encode(), "criador", "codex-titular")["acao"], "login")
        t = ns["montar_pedido"](["--trazer", "t-20261109-abc123"])                         # F10: listar a saída retida de um id
        self.assertEqual(set(t), {"schema_version", "id", "acao", "retida"})
        self.assertEqual(J.validar_pedido(json.dumps(t).encode(), "criador", "codex-titular")["retida"], "t-20261109-abc123")
        for ruim in (["login"], ["--login", "x"], ["-x"], ["--prompt", "oi"], ["oi"], ["--sandbox", "danger-full-access"],
                     ["--trazer"], ["--trazer", "../x"], ["--trazer", "ABCDEFGH1"], ["--trazer", "t-20261109-abc123", "x"],
                     ["--trazer", "t-20261109-abc123\n"]):
            with self.subTest(ruim), self.assertRaises(SystemExit):
                ns["montar_pedido"](ruim)

    def test_o_lancador_chama_so_o_sudo_com_o_argv_fixo_e_o_login_leva_o_pedido_e_o_rotulo(self):
        _, ns = self.lancador()
        rc, chamadas, saida, erro = self.executar(ns, [], resposta={"ok": True})
        argv, kw = chamadas[0]
        self.assertEqual(argv, ["/usr/bin/sudo", "-u", "fundacao-jaula", "--", "/usr/local/lib/fundacao-ia/jaula/1.7.11/jaula-entrar",
                                "criador", "codex-titular"])
        self.assertEqual((rc, kw["input"], kw["cwd"], kw["env"]["TERM"]), (0, None, "/", "xterm"))
        self.assertIn("Pronto: o Codex foi fechado.", saida)
        self.assertIn("vão à OpenAI", erro)
        self.assertIn("retido na jaula", erro)
        rc, chamadas, saida, erro = self.executar(ns, ["--login"])
        self.assertEqual(json.loads(chamadas[0][1]["input"])["acao"], "login")
        self.assertEqual(chamadas[0][0][-2:], ["criador", "codex-titular"])                    # o MESMO argv: a sudoers não ganha linha
        self.assertIn("conta INTEIRA", erro)
        rc, _, saida, _ = self.executar(ns, ["--login"], codigo=2, resposta={"ok": False, "erro": "recusa de ensaio"})
        self.assertEqual(rc, 1)
        self.assertIn("recusa de ensaio", saida)
        self.assertEqual(self.executar(ns, [], euid=0)[0], 2)                                  # com sudo na frente, não roda

    # --- F10: a confirmação do titular --------------------------------------------------------------------------------
    PENDENTE = {"retida": "t-20261109-abc123", "destino": "outputs/codex/t-20261109-abc123", "voltou": False,
                "pendente": [{"arquivo": "resultado.md", "sha256": "a" * 64, "bytes": 6},
                             {"arquivo": "sub/b.txt", "sha256": "b" * 64, "bytes": 2},
                             {"arquivo": "esc\x1b[31mape.txt", "sha256": "c" * 64, "bytes": 1}],
                "lista_sha256": "d" * 64, "recusados": [], "recusados_total": 0,
                "onde": "/var/lib/fundacao-ia/jaula/criador/codex/retida/t-20261109-abc123"}

    def executar_seq(self, ns, argv, respostas, tecla):
        """Roda o lançador com uma resposta por chamada à entrada fixa e a tecla do titular simulada (nada espera entrada)."""
        chamadas, restantes, perguntas = [], list(respostas), []

        def run(args, **kw):
            chamadas.append((list(args), kw))
            resposta, codigo = restantes.pop(0)
            return types.SimpleNamespace(returncode=codigo, stdout=json.dumps(resposta).encode())

        def ler_tecla():
            perguntas.append(True)
            return tecla
        ns["subprocess"] = types.SimpleNamespace(run=run, PIPE=-1)
        ns["os"] = types.SimpleNamespace(environ={"TERM": "xterm"}, geteuid=lambda: 1000)
        with contextlib.redirect_stdout(io.StringIO()) as saida, contextlib.redirect_stderr(io.StringIO()) as erro:
            rc = ns["main"](argv, ler_tecla=ler_tecla)
        return rc, chamadas, saida.getvalue(), erro.getvalue(), len(perguntas)

    def test_f10_sem_a_tecla_do_titular_nada_volta_e_a_mensagem_diz_onde_ficou_e_como_trazer(self):
        _, ns = self.lancador()
        for tecla in ("", "n", "N", "\n", "x"):
            with self.subTest(tecla=tecla):
                rc, chamadas, saida, _erro, perguntas = self.executar_seq(ns, [], [({"ok": True, "saida": self.PENDENTE}, 0)], tecla)
                self.assertEqual((rc, len(chamadas), perguntas), (0, 1, 1))                 # só a chamada do Codex: nada foi trazido
                self.assertIsNone(chamadas[0][1]["input"])                                  # o terminal herda o do titular
                self.assertIn("Nada voltou ao projeto", saida)
                self.assertIn(self.PENDENTE["onde"], saida)
                self.assertIn("abrir-codex-criador --trazer t-20261109-abc123", saida)
        self.assertIn("3 arquivo(s), 9 byte(s)", saida)                                     # a lista com os tamanhos
        for linha in ("         6 bytes  'resultado.md'", "         2 bytes  'sub/b.txt'"):
            self.assertIn(linha, saida)
        self.assertNotIn(chr(27), saida)                                                    # nome com escape de terminal vem escapado
        self.assertIn("\\x1b[31m", saida)

    def test_f10_com_a_tecla_s_pede_a_jaula_so_a_lista_mostrada(self):
        _, ns = self.lancador()
        volta = {"ok": True, "saida": {"destino": self.PENDENTE["destino"], "voltou": True, "retida": None,
                                       "copiados": self.PENDENTE["pendente"], "recusados_total": 0}}
        rc, chamadas, saida, _erro, perguntas = self.executar_seq(
            ns, [], [({"ok": True, "saida": self.PENDENTE}, 0), (volta, 0)], "s")
        self.assertEqual((rc, len(chamadas), perguntas), (0, 2, 1))
        segundo = chamadas[1]
        self.assertEqual(segundo[0][-2:], ["criador", "codex-titular"])                     # o MESMO argv: a sudoers não ganha linha
        pedido = json.loads(segundo[1]["input"])
        self.assertEqual((pedido["acao"], pedido["retida"], pedido["lista_sha256"]), ("trazer", "t-20261109-abc123", "d" * 64))
        self.assertEqual(set(pedido), {"schema_version", "id", "acao", "retida", "lista_sha256"})
        self.assertEqual(J.validar_pedido(json.dumps(pedido).encode(), "criador", "codex-titular")["acao"], "trazer")
        self.assertIn("3 arquivo(s) foram para outputs/codex/t-20261109-abc123", saida)
        recusa = {"ok": False, "erro": "a lista retida não é a que você confirmou"}      # a jaula recusou
        rc, _, saida, _erro, _ = self.executar_seq(ns, [], [({"ok": True, "saida": self.PENDENTE}, 0), (recusa, 2)], "s")
        self.assertEqual(rc, 1)
        self.assertIn("não é a que você confirmou", saida)
        self.assertIn("--trazer t-20261109-abc123", saida)

    def test_f10_trazer_depois_lista_primeiro_e_so_traz_com_a_tecla(self):
        _, ns = self.lancador()
        listada = {"ok": True, "saida": {k: v for k, v in self.PENDENTE.items() if k not in ("onde", "recusados", "recusados_total")}}
        rc, chamadas, saida, erro, perguntas = self.executar_seq(ns, ["--trazer", "t-20261109-abc123"], [(listada, 0)], "n")
        self.assertEqual((rc, len(chamadas), perguntas), (0, 1, 1))
        pedido = json.loads(chamadas[0][1]["input"])
        self.assertEqual((pedido["acao"], pedido["retida"]), ("listar", "t-20261109-abc123"))
        self.assertNotIn("OpenAI", erro)
        self.assertIn("Nada voltou ao projeto", saida)
        sem_lista = [({"ok": False, "erro": "não há saída retida com o id"}, 2)]
        rc, _, saida, _erro, perguntas = self.executar_seq(ns, ["--trazer", "t-20261109-abc123"], sem_lista, "s")
        self.assertEqual((rc, perguntas), (1, 0))                                           # sem lista, nem pergunta
        self.assertIn("não há saída retida", saida)

    def test_f10_sem_arquivo_para_trazer_nao_pergunta_nada(self):
        _, ns = self.lancador()
        vazia = {**self.PENDENTE, "pendente": [], "onde": None, "recusados_total": 2}
        rc, chamadas, saida, _erro, perguntas = self.executar_seq(ns, [], [({"ok": True, "saida": vazia}, 0)], "s")
        self.assertEqual((rc, len(chamadas), perguntas), (0, 1, 0))
        self.assertIn("Nada para trazer", saida)

    def test_f10_a_tecla_vem_do_terminal_do_titular_nunca_da_entrada_padrao(self):
        texto, ns = self.lancador()
        self.assertNotIn("sys.stdin", texto)
        self.assertNotIn("input(", texto)
        abertos = []

        class Terminal:
            def __init__(self, dados):
                self.dados = dados

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def fileno(self):
                raise io.UnsupportedOperation("sem descritor no ensaio")

            def read(self, n):
                return self.dados[:n]

            def readline(self):
                return self.dados

        def abrir(caminho, modo="r", **kw):
            abertos.append((caminho, modo))
            return Terminal(b"S\n")
        ns["open"] = abrir
        self.assertEqual(ns["ler_tecla_do_terminal"](), "s")
        self.assertEqual(abertos, [("/dev/tty", "r+b")])
        ns["open"] = mock.Mock(side_effect=OSError("sem terminal"))                          # sem terminal: não confirmou
        self.assertEqual(ns["ler_tecla_do_terminal"](), "")

    def test_o_lancador_recusa_valor_que_vira_codigo(self):
        for projeto in ("Ruim", "a--b", "x'; import os #", "../x"):
            with self.subTest(projeto), self.assertRaises(self.m.EntradaInvalida):
                self.pj.texto_do_lancador_codex(projeto, "/usr/local/lib/x")
        for programas in ("/usr/local/lib/x'y", "/usr/local/lib/x\\y", "/usr/local/lib/x\ny"):
            with self.subTest(programas), self.assertRaises(self.m.EntradaInvalida):
                self.pj.texto_do_lancador_codex("criador", programas)

    # --- o plano e a instalação da jaula com o Codex ---------------------------------------------------------------
    def area(self, **secoes):
        ab = ficha_aplicada(self.m, **secoes)
        gravar_area(self.base, self.m, ab, self.caminhos)
        return ab

    def montar(self):
        return self.pj.montar_plano(SKILL, self.base / "area", ["caso-real"], USUARIO_DO_ENSAIO, self.caminhos)

    def aprovar(self, plano, aprovados):
        rel = {"schema_version": J.ESQUEMA_RELATORIO_INSTALADO, "hashes": plano["hashes_previstos"],
               "modos": {c: {"aprovado": True} for c in aprovados}}
        destino = Path(self.caminhos.etc) / J.RELATORIO_INSTALADO
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(rel), encoding="utf-8")

    def test_o_lancador_e_a_linha_da_sudoers_so_existem_com_o_canario_aprovado_e_saem_quando_ele_revoga(self):
        self.area(outras_llm=secao_codex(autenticacao="chave_api"))
        plano = self.montar()
        self.assertTrue(plano["codex"])
        self.assertEqual((plano["lancadores"], plano["pares"]), ([], [("caso-real", "canario")]))
        for trecho in ("instalar-codex-jaula", "conta INTEIRA", "saída para qualquer destino"):   # o rótulo do risco, antes de instalar
            self.assertIn(trecho, "\n".join(self.pj.texto_do_plano(plano)))
        self.assertNotIn("codex-", plano["sudoers"].split("Defaults!")[1])                  # sem canário, sem linha do Codex
        self.aprovar(plano, ("codex-exec", "codex-titular"))
        plano = self.montar()
        self.assertEqual(plano["pares"], [("caso-real", "canario"), ("caso-real", "codex-exec"), ("caso-real", "codex-titular")])
        for modo in ("codex-exec", "codex-titular"):
            self.assertRegex(plano["sudoers"], rf"(?m)^{USUARIO_DO_ENSAIO} .* caso-real {modo}$")
        res = self.pj.instalar_jaula(plano, rodar=VisudoFalso())
        lancador = Path(self.caminhos.bin) / "abrir-codex-caso-real"
        self.assertEqual([a["acao"] for a in res["acoes"] if a["item"].startswith("lancador")], ["criar"])
        self.assertEqual(lancador.read_text(encoding="utf-8"), plano["lancadores"][0]["texto"])
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(lancador.stat().st_mode), 0o755)
        self.assertEqual([a["acao"] for a in self.pj.instalar_jaula(self.montar(), rodar=VisudoFalso())["acoes"]
                          if a["item"].startswith("lancador")], ["igual"])
        self.aprovar(plano, ("codex-exec",))                                                # o canário revogou o modo do titular
        res = self.pj.instalar_jaula(self.montar(), rodar=VisudoFalso())
        self.assertEqual([a["acao"] for a in res["acoes"] if a["item"].startswith("lancador")], ["remover"])
        self.assertFalse(lancador.exists())
        lancador.write_text("#!/bin/sh\necho meu\n", encoding="utf-8")                       # arquivo que não é do preparo fica
        self.pj.instalar_jaula(self.montar(), rodar=VisudoFalso())
        self.assertTrue(lancador.exists())

    def test_n_cdx_1_sem_outras_llm_na_ficha_nao_ha_linha_nem_lancador_nem_download_do_codex(self):
        self.area(navegador={"dominios": ["esaj.exemplo.org"], "logins": [], "modos": ["sessao"]})
        plano = self.montar()
        self.assertFalse(plano["codex"])
        self.assertNotIn("download do Codex", "\n".join(self.pj.texto_do_plano(plano)))
        self.aprovar(plano, ("navegador", "codex-exec", "codex-titular"))                   # nem um relatório que aprove o resto muda isso
        plano = self.montar()
        self.assertEqual(plano["pares"], [("caso-real", "canario"), ("caso-real", "navegador")])
        self.assertEqual(plano["lancadores"], [])
        self.assertEqual(self.pj.instalar_codex_jaula(SKILL, self.caminhos, plano, simular=True), {"acoes": [], "necessaria": False})
        self.assertTrue(self.pj.instalar_codex_jaula(SKILL, self.caminhos, {**plano, "codex": True}, simular=True)["necessaria"])


class SondaM7DoCodex(_Entrar):
    """A sonda do sandbox próprio do Codex (M7): o `codex sandbox -- <comando>` do binário fixado, rodado pelo canário dentro da
    jaula; o motivo do item vira a medida `sandbox_codex` no relatório de dono root, que a entrada fixa consome."""

    def setUp(self):
        super().setUp()
        self.canario = carregar_por_caminho("_canario_codex_teste", WSL / "canario_jaula.py")
        self.codex = self.base / "codex"
        self.codex.write_bytes(b"#!/bin/sh\n")
        os.chmod(self.codex, 0o755)
        self.chamadas = []

    def falso(self, abre=True, confina=True, saida=b"bwrap: setting up uid map: Permission denied\n"):
        """Um `codex sandbox` falso: não abre (código 1 e mensagem), ou abre e confina (só /bin/true passa) ou abre e não confina."""
        def rodar(argv, **kw):
            self.chamadas.append((list(argv), kw))
            comando = argv[argv.index("--") + 1:]
            codigo = 0 if abre and (not confina or comando == ["/bin/true"]) else 1
            return types.SimpleNamespace(returncode=codigo, stderr=saida if not abre else b"")
        return rodar

    def item(self, **kw):
        return self.canario.prova_sandbox_codex(str(self.codex), rodar=self.falso(**kw))

    def test_o_codex_falso_que_abre_e_confina_vira_aberto_e_sem_medida(self):
        i = self.item()
        self.assertEqual((i["id"], i["aprovado"], i["informativo"]), ("sandbox_codex", True, True))
        self.assertTrue(i["motivo"].startswith(J.SANDBOX_CODEX_ABERTO) and "confinou a rede e a escrita" in i["motivo"])
        self.assertEqual(J.medidas_dos_itens_do_codex([i]), {})                         # aberto: vale o padrão (sandbox ligado)
        primeira, kw = self.chamadas[0]
        self.assertEqual(primeira, [str(self.codex), "sandbox", "--", "/bin/true"])      # o subcomando que a versão fixada tem
        self.assertEqual((kw["cwd"], kw["timeout"], kw["stdin"]), ("/trabalho/saida", self.canario.PRAZO_DA_SONDA_S, subprocess.DEVNULL))
        self.assertLessEqual(set(kw["env"]), {"PATH", "HOME", "TMPDIR", "LANG", "CODEX_HOME"})
        self.assertEqual(len(self.chamadas), 3)                                           # /bin/true, rede e escrita fora

    def test_o_que_abre_mas_nao_confina_diz_quais_fugas_e_nao_muda_a_medida(self):
        i = self.item(confina=False)
        self.assertTrue(i["aprovado"] and i["motivo"].startswith(J.SANDBOX_CODEX_ABERTO))
        self.assertIn("NÃO confinou: rede, escrita fora da pasta de trabalho", i["motivo"])
        self.assertEqual(J.medidas_dos_itens_do_codex([i]), {})

    def test_o_codex_falso_que_nao_abre_o_sandbox_vira_danger_full_access_com_o_motivo(self):
        i = self.item(abre=False)
        self.assertEqual((i["aprovado"], i["informativo"]), (True, True))                # não reprova o modo: a barreira é a jaula
        self.assertTrue(i["motivo"].startswith(J.SANDBOX_CODEX_RECUSADO))
        self.assertIn("Permission denied", i["motivo"])
        self.assertIn("só a jaula", i["motivo"])
        self.assertEqual(J.medidas_dos_itens_do_codex([i]), {"sandbox_codex": "danger-full-access"})
        self.assertEqual(len(self.chamadas), 1)                                           # recusou no /bin/true: não testa o resto

    def test_sem_binario_prazo_estourado_ou_falha_de_execucao_reprova_e_nunca_vira_medida(self):
        i = self.canario.prova_sandbox_codex(str(self.base / "nao-existe"), rodar=self.falso())
        self.assertFalse(i["aprovado"])
        self.assertIn("nada foi medido", i["motivo"])
        self.assertFalse(self.canario.prova_sandbox_codex("", rodar=self.falso())["aprovado"])

        def estoura(argv, **kw):
            raise subprocess.TimeoutExpired(argv, kw["timeout"])
        for rodar in (estoura, mock.Mock(side_effect=OSError("sem exec"))):
            i = self.canario.prova_sandbox_codex(str(self.codex), rodar=rodar)
            self.assertFalse(i["aprovado"])
            self.assertEqual(J.medidas_dos_itens_do_codex([{**i, "motivo": J.SANDBOX_CODEX_RECUSADO}]), {})   # reprovado nunca é medida

    def test_os_textos_do_canario_e_da_entrada_fixa_sao_os_mesmos_e_a_medida_so_le_o_item_certo(self):
        self.assertEqual((self.canario.SANDBOX_CODEX_ABERTO, self.canario.SANDBOX_CODEX_RECUSADO),
                         (J.SANDBOX_CODEX_ABERTO, J.SANDBOX_CODEX_RECUSADO))
        recusado = {"id": "sandbox_codex", "aprovado": True, "motivo": J.SANDBOX_CODEX_RECUSADO + " (código 1)"}
        for lixo in (None, [], "x", [3], [{"id": "userns", "aprovado": True, "motivo": J.SANDBOX_CODEX_RECUSADO}],
                     [{**recusado, "aprovado": False}], [{**recusado, "motivo": 7}]):
            self.assertEqual(J.medidas_dos_itens_do_codex(lixo), {}, lixo)
        self.assertEqual(J.medidas_dos_itens_do_codex([recusado]), {"sandbox_codex": "danger-full-access"})

    def test_a_medida_entra_no_relatorio_de_dono_root_e_a_entrada_fixa_a_consome_com_o_rotulo(self):
        m = carregar_preparo()
        pj, base = m.preparo_jaula(), self.base / "inst"
        (base / "jaula-ensaio").mkdir(parents=True)
        caminhos = pj.caminhos_de_ensaio(base / "jaula-ensaio", base / "area")
        for nome in ("jaula-entrar", "proxy_lista.py"):
            Path(caminhos.programas).mkdir(parents=True, exist_ok=True)
            (Path(caminhos.programas) / nome).write_bytes(nome.encode())
        Path(caminhos.bwrap).write_bytes(b"bwrap de ensaio\n")
        cfg = J.Config(programas=caminhos.programas, estado=caminhos.estado, etc=caminhos.etc, bwrap=caminhos.bwrap, usuario=None)
        atuais = J.hashes_da_instalacao(cfg)

        def resposta(como, i):
            itens = [{"id": n, "aprovado": True, "motivo": "ok", "informativo": False} for n in pj.ids_do_canario(como)]
            itens = [i if x["id"] == "sandbox_codex" else x for x in itens]
            return guardar_resposta_do_canario(caminhos, json.dumps(
                {"schema_version": J.ESQUEMA_RESPOSTA, "modo": "canario", "como": como, "id": "c-" + como, "ok": True,
                 "projeto": "criador", "hashes": atuais,
                 "relatorio": {"schema_version": J.ESQUEMA_RELATORIO, "como": como, "itens": itens, "gerado_em": "2026-11-08",
                               "aprovado": True}}).encode())   # F3: a jaula guarda a mesma resposta no estado
        i_recusado = {"id": "sandbox_codex", "aprovado": True, "informativo": True, "motivo": J.SANDBOX_CODEX_RECUSADO + " (código 1)"}
        i_aberto = {"id": "sandbox_codex", "aprovado": True, "informativo": True, "motivo": J.SANDBOX_CODEX_ABERTO + " e confinou"}
        res = pj.instalar_canario_jaula([io.BytesIO(resposta("codex-exec", i_recusado)), io.BytesIO(resposta("codex-titular", i_aberto))],
                                        caminhos, raiz_dono=False, hoje="2026-11-08")
        instalado = json.loads((Path(caminhos.etc) / J.RELATORIO_INSTALADO).read_text(encoding="utf-8"))
        self.assertEqual(instalado["modos"]["codex-exec"]["medidas"], {"sandbox_codex": "danger-full-access"})
        self.assertNotIn("medidas", instalado["modos"]["codex-titular"])                  # aberto: nada a registrar
        texto = "\n".join(pj.texto_do_canario(res))
        self.assertIn("ATENÇÃO: " + J.ROTULO_SEM_SANDBOX_DO_CODEX, texto)
        self.assertEqual(texto.count("ATENÇÃO"), 1)
        self.assertIn("única barreira é a jaula", J.ROTULO_SEM_SANDBOX_DO_CODEX)
        self.assertEqual(J.medidas_do_codex(instalado, "codex-exec"), {"sandbox_codex": "danger-full-access"})
        self.assertEqual(J.medidas_do_codex(instalado, "codex-titular"), {"sandbox_codex": "workspace-write"})
        self.relatorio = instalado                                                       # e a entrada fixa usa a medida do root
        self.relatorio["hashes"] = HASHES
        self.relatorio["modos"]["codex-exec"]["aprovado"] = self.relatorio["modos"]["codex-titular"]["aprovado"] = True
        r = self.entrar()
        self.assertIn('sandbox_mode = "danger-full-access"', self.visto["config"])
        self.assertEqual(r["aviso_sandbox"], J.ROTULO_SEM_SANDBOX_DO_CODEX)               # o rótulo vai na resposta do pedido
        self.assertNotIn("aviso_sandbox", self.entrar("codex-titular"))

    def test_o_canario_do_codex_monta_o_binario_e_o_config_imposto_e_mede_com_o_sandbox_padrao(self):
        self.relatorio["modos"]["codex-exec"]["medidas"] = {"sandbox_codex": "danger-full-access"}   # a medida anterior não conta
        with mock.patch.object(J, "_isca_abstrata", return_value=(mock.Mock(), "isca-teste")):   # o AF_UNIX abstrato é do Linux
            r = J.entrar(self.cfg, "criador", "canario", pedido(como="codex-exec", dominios=["api.openai.com"]),
                         raiz=str(self.raiz), ficha=self.ficha, relatorio=self.relatorio, hoje=HOJE, hashes_atuais=HASHES)
        guardada = self.estado_p / "canario" / "pedido-cdx-0001.json"      # F3: a jaula guarda a resposta onde a sessão não alcança
        self.assertEqual(guardada.read_bytes(), J.texto_da_resposta(r).encode("utf-8"))
        self.assertEqual((r["projeto"], r["id"], r["como"]), ("criador", "pedido-cdx-0001", "codex-exec"))
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(guardada.stat().st_mode), 0o600)
        argv = self.rodadas[0]
        codex = f"{self.cfg.programas}/codex/0.166.0/codex"
        self.assertIn([f"{self.cfg.programas}/codex"] * 2, [argv[i + 1:i + 3] for i, x in enumerate(argv) if x == "--ro-bind"])
        comando = argv[argv.index("--") + 1:]
        self.assertEqual(comando[comando.index("--codex") + 1], codex)                    # o canário recebe o binário fixado
        self.assertIn('sandbox_mode = "workspace-write"', self.visto["config"])           # medir é com o padrão, nunca com a medida
        self.assertIn('approval_policy = "never"', self.visto["config"])
        self.assertIn("/home/jaula/codex/config.toml", argv)
        self.assertNotIn("/home/jaula/codex", [argv[i + 2] for i, x in enumerate(argv) if x == "--bind"])   # canário: sem estado privado
        sem_codex = J.perfil_do_modo("canario", None, "navegador")
        self.assertEqual(J.PROGRAMAS_DO_MODO["canario-codex"], ("codex",))
        self.assertNotIn(f"{self.cfg.programas}/codex",
                         J.montar_argv(self.cfg, "criador", "pedido-cdx-0001", sem_codex, ["x"], fds={d: 1 for d in J.DADOS_GERADOS},
                                       existe=lambda p: True, sistema=[["ro-bind", "/usr", "/usr"]]))   # o do navegador não o leva


FALSO_CODEX = """#!/bin/sh
echo "ARGV $*"
echo "PROMPT_NO_AMBIENTE ${FUNDACAO_PROMPT-ausente}"
echo "STDIN_INICIO"; cat; echo "STDIN_FIM"
echo "CODEX_HOME_TEM $(ls /home/jaula/codex | tr '\\n' ' ')"
echo "APROVACAO $(grep -c 'approval_policy = "never"' /home/jaula/codex/config.toml)"
( : > /home/jaula/codex/config.toml ) 2>/dev/null && echo CONFIG_GRAVOU || echo CONFIG_SO_LEITURA
( : > /trabalho/projeto/x ) 2>/dev/null && echo PROJETO_GRAVOU || echo PROJETO_SO_LEITURA
echo feito > /trabalho/saida/resposta.txt
[ -e /mnt ] && echo TEM_MNT || echo SEM_MNT
"""


FALSO_SANDBOX = """#!/bin/sh
# codex falso: so entende "codex sandbox -- <comando>"; com o arquivo "recusa" ao lado, o sandbox "nao abre"
[ "$1" = sandbox ] || exit 64
shift
[ "$1" = -- ] && shift
if [ -e "$(dirname "$0")/recusa" ]; then echo "bwrap: setting up uid map: Permission denied" >&2; exit 1; fi
exec "$@"
"""


@unittest.skipUnless(sys.platform.startswith("linux"), "o pty e a caixa são do Linux")
class CodexNaJaulaLinux(unittest.TestCase):
    """L: o pty do terminal do Codex e um Codex FALSO montado na caixa de verdade (pulam com o motivo quando falta o bwrap)."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="jaula-cdx-linux-1711-")).resolve()
        self.addCleanup(shutil.rmtree, self.base, True)

    def test_o_terminal_do_codex_roda_num_pty_proprio_e_a_tela_sai_pelo_stderr(self):
        if not os.path.exists("/dev/ptmx"):
            self.skipTest("sem /dev/ptmx neste ambiente")
        codigo = ("import importlib.util, json, sys\n"
                  "s = importlib.util.spec_from_file_location('jaula', sys.argv[1])\n"
                  "m = importlib.util.module_from_spec(s)\ns.loader.exec_module(m)\n"
                  "r = m.rodar_com_pty(['/bin/sh', '-c', 'echo da-tela; tty; exit 3'], m.limites_do_modo(m.PERFIS['codex-titular']))\n"
                  "print(json.dumps({'codigo': r['codigo']}))\n")
        r = subprocess.run([sys.executable, "-I", "-B", "-c", codigo, str(WSL / "jaula.py")], stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace")[-400:])
        self.assertEqual(json.loads(r.stdout.decode("utf-8")), {"codigo": 3})            # o stdout fica só com a resposta
        tela = r.stderr.decode("utf-8", "replace")
        self.assertIn("da-tela", tela)
        self.assertRegex(tela, "/dev/pts/[0-9]+")                                        # o Codex vê um terminal que é o pty da jaula

    def test_o_codex_falso_na_caixa_recebe_o_prompt_pela_entrada_padrao_e_o_config_so_leitura(self):
        if MOTIVO:
            if EXIGE:
                raise AssertionError(f"FUNDACAO_CI_EXIGE_BWRAP=1 e não há bwrap utilizável: {MOTIVO}")
            self.skipTest(MOTIVO)
        cfg = J.Config(bwrap=shutil.which("bwrap"), estado=str(self.base / "estado"), programas=str(self.base / "prog"),
                       python="/usr/bin/python3", usuario=None)
        estado = self.base / "estado" / "criador"
        trabalho = estado / "trabalho" / "pedido-cdx-0001"
        for sub in ("proxy", "codex/home", "trabalho/pedido-cdx-0001/saida", "trabalho/pedido-cdx-0001/projeto"):
            (estado / sub).mkdir(parents=True)
        (estado / "proxy" / "proxy.sock").touch()                                        # a ponte do proxy não é o assunto aqui
        (estado / "codex" / "home" / "auth.json").write_text("{}", encoding="utf-8")
        codex = Path(J.programa_do_codex(cfg))
        codex.parent.mkdir(parents=True)
        codex.write_text(FALSO_CODEX, encoding="utf-8")
        os.chmod(codex, 0o755)
        (trabalho / "codex-config.toml").write_bytes(J.config_do_codex("codex-exec", {}))
        (trabalho / "projeto" / "arquivo.txt").write_text("do projeto", encoding="utf-8")
        perfil = J.perfil_do_modo("codex-exec")
        comando, extras = J.comando_do_codex(cfg, "codex-exec", {"prompt": "resuma o contrato sigiloso\ncom duas linhas"})
        _, secretas = J.ambiente_do_modo(cfg, perfil, extras=extras)
        fds = {d: J._memfd("jaula", dados) for d, dados in J.conteudos_gerados(os.getuid(), os.getgid()).items()}
        fds["args"] = J._memfd("jaula-args", J.args_secretos(secretas))
        self.addCleanup(lambda: [os.close(fd) for fd in fds.values()])
        argv = J.montar_argv(cfg, "criador", "pedido-cdx-0001", perfil, comando, fds=fds, extras=extras)
        r = subprocess.run(argv, capture_output=True, env={}, pass_fds=tuple(fds.values()), timeout=90)
        saida = r.stdout.decode("utf-8", "replace")
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace")[-500:])
        self.assertIn("ARGV exec --strict-config --skip-git-repo-check --ephemeral --ignore-rules --color never -C /trabalho/saida -",
                      saida)
        self.assertNotIn("sigiloso", saida.split("STDIN_INICIO")[0])                       # o prompt não está no argv
        self.assertIn("PROMPT_NO_AMBIENTE ausente", saida)                               # ...nem no ambiente do Codex
        entrada = saida.split("STDIN_INICIO")[1].split("STDIN_FIM")[0]
        self.assertIn(J.PREFACIO_DO_CODEX, entrada)
        self.assertIn("resuma o contrato sigiloso\ncom duas linhas", entrada)              # ...e sim na entrada padrão
        self.assertIn("auth.json config.toml", saida)                                    # o CODEX_HOME privado e o config montado
        self.assertIn("APROVACAO 1", saida)
        for esperado in ("CONFIG_SO_LEITURA", "PROJETO_SO_LEITURA", "SEM_MNT"):
            self.assertIn(esperado, saida)
        self.assertEqual((trabalho / "saida" / "resposta.txt").read_text(encoding="utf-8"), "feito\n")
        self.assertEqual((trabalho / "projeto").joinpath("arquivo.txt").read_text(encoding="utf-8"), "do projeto")
        self.assertIn('approval_policy = "never"', (trabalho / "codex-config.toml").read_text(encoding="utf-8"))   # o modelo não mudou


    def sonda_na_caixa(self, recusa: bool) -> dict:
        """Roda a sonda M7 do canário (`prova_sandbox_codex`) na caixa do canário do Codex, com um `codex sandbox` FALSO que
        abre (executa o comando, sem confinar nada) ou que recusa abrir (como o bwrap do Codex sob --disable-userns)."""
        if MOTIVO:
            if EXIGE:
                raise AssertionError(f"FUNDACAO_CI_EXIGE_BWRAP=1 e não há bwrap utilizável: {MOTIVO}")
            self.skipTest(MOTIVO)
        cfg = J.Config(bwrap=shutil.which("bwrap"), estado=str(self.base / "estado"), programas=str(self.base / "prog"),
                       python="/usr/bin/python3", usuario=None)
        estado = self.base / "estado" / "criador"
        trabalho = estado / "trabalho" / "pedido-cdx-0001"
        for sub in ("proxy", "trabalho/pedido-cdx-0001/saida", "trabalho/pedido-cdx-0001/projeto"):
            (estado / sub).mkdir(parents=True)
        (estado / "proxy" / "proxy.sock").touch()
        codex = Path(J.programa_do_codex(cfg))
        codex.parent.mkdir(parents=True)
        codex.write_text(FALSO_SANDBOX, encoding="utf-8")
        os.chmod(codex, 0o755)
        if recusa:
            (codex.parent / "recusa").write_text("", encoding="utf-8")
        shutil.copy(WSL / "canario_jaula.py", Path(cfg.programas) / "canario_jaula.py")
        (trabalho / "codex-config.toml").write_bytes(J.config_do_codex("codex-exec", {}))      # o canário monta o config imposto
        perfil = J.perfil_do_modo("canario", None, "codex-exec")
        codigo = ("import importlib.util, json, sys\n"
                  "s = importlib.util.spec_from_file_location('c', sys.argv[1])\nm = importlib.util.module_from_spec(s)\n"
                  "s.loader.exec_module(m)\nprint(json.dumps(m.prova_sandbox_codex(sys.argv[2])))\n")
        comando = ["/usr/bin/python3", "-I", "-B", "-c", codigo, f"{cfg.programas}/canario_jaula.py", str(codex)]
        fds = {d: J._memfd("jaula", dados) for d, dados in J.conteudos_gerados(os.getuid(), os.getgid()).items()}
        self.addCleanup(lambda: [os.close(fd) for fd in fds.values()])
        argv = J.montar_argv(cfg, "criador", "pedido-cdx-0001", perfil, comando, fds=fds)
        self.assertIn("/home/jaula/codex/config.toml", argv)                                     # o config imposto foi montado
        r = subprocess.run(argv, capture_output=True, env={}, pass_fds=tuple(fds.values()), timeout=180)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace")[-500:])
        return json.loads(r.stdout.decode("utf-8"))

    def test_sonda_m7_na_caixa_com_o_codex_falso_que_abre_o_sandbox(self):
        i = self.sonda_na_caixa(recusa=False)
        self.assertEqual((i["id"], i["aprovado"]), ("sandbox_codex", True))
        self.assertTrue(i["motivo"].startswith(J.SANDBOX_CODEX_ABERTO), i)
        self.assertIn("escrita fora da pasta de trabalho", i["motivo"])                         # o falso não confina: a sonda o diz
        self.assertEqual(J.medidas_dos_itens_do_codex([i]), {})

    def test_sonda_m7_na_caixa_com_o_codex_falso_que_nao_abre_o_sandbox(self):
        i = self.sonda_na_caixa(recusa=True)
        self.assertTrue(i["aprovado"] and i["motivo"].startswith(J.SANDBOX_CODEX_RECUSADO), i)
        self.assertIn("Permission denied", i["motivo"])
        self.assertEqual(J.medidas_dos_itens_do_codex([i]), {"sandbox_codex": "danger-full-access"})


if __name__ == "__main__":
    unittest.main()
