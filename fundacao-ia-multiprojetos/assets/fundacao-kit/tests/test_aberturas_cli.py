"""CLI da ficha de aberturas (1.7.10, contratos do lote 2, §5): `abertura preparar|verificar|vigente`.

O parser de teste é o do `__main__`, que registra `cli_aberturas` no laço das extensões desde a integração (item I2:
`registrar_parser(sub).set_defaults(func=cmd_extensao, executor=executar)`; antes dela, o teste o registrava do mesmo
jeito). Raiz descartável, projetos e identidades de ensaio, âncora e chaves de ensaio."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import unittest
from pathlib import Path
from unittest import mock

from helpers import FoundationTestCase
from test_aberturas_disco import ligar_pasta
from test_aberturas_regras import ficha
from test_aberturas_vigente import Assinador

from fundacao import KIT_VERSION
from fundacao import __main__ as principal
from fundacao import cli_aberturas
from fundacao.core import aberturas, aberturas_comando, decisoes, events
from fundacao.core import aberturas_regras as regras
from fundacao.core.auth import ENV_PRINCIPAL
from fundacao.core.contracts import FundacaoError


def rascunho(**extra) -> dict:
    f = ficha(**extra)
    for campo in ("versao", "ficha_id"):
        f.pop(campo, None)
    return f


class AberturasCliCase(FoundationTestCase):
    def setUp(self):
        super().setUp()
        self.base_chaves = self.root.parent / (self.root.name + "-chaves")
        self.assinador = Assinador(self.base_chaves)
        padrao = mock.patch.object(decisoes, "ANCORAS_PADRAO", (str(self.assinador.ancora),))
        padrao.start()
        self.addCleanup(padrao.stop)
        self.addCleanup(shutil.rmtree, self.base_chaves, ignore_errors=True)
        self.pasta = self.root / "projects" / "juridico-lab"
        self.rascunhos = self.pasta / "outputs" / "aberturas"

    def parser(self) -> argparse.ArgumentParser:
        return principal.build_parser()  # com `abertura` no laço das extensões (item I2 da integração)

    def cli(self, quem, *argv, ambiente=None) -> tuple[int, dict]:
        with mock.patch.dict(os.environ, {}):
            for nome in (ENV_PRINCIPAL, cli_aberturas.ENV_TRAVA, cli_aberturas.ENV_RAIZ):
                os.environ.pop(nome, None)
            if quem:
                os.environ[ENV_PRINCIPAL] = quem
            os.environ.update(ambiente or {})
            args = self.parser().parse_args(["--raiz", str(self.root), *argv])
            args.raiz = args.raiz.resolve()
            try:
                return 0, json.loads(json.dumps(args.func(args), default=str))
            except FundacaoError as exc:
                return 2, exc.as_dict()

    def escrever_rascunho(self, dados: dict, nome: str = "rascunho.json") -> Path:
        alvo = self.pasta / "outputs" / nome
        alvo.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        return alvo

    def preparar(self, dados=None, quem="operador-juridico", **kw) -> tuple[int, dict]:
        arquivo = self.escrever_rascunho(dados if dados is not None else rascunho())
        return self.cli(quem, "abertura", "preparar", "--projeto", "juridico-lab", "--rascunho",
                        str(arquivo.relative_to(self.pasta)), **kw)


class TestParser(AberturasCliCase):
    def test_vigente_troca_o_func_do_laco_e_as_outras_acoes_ficam_com_ele(self):
        p = self.parser()
        self.assertIs(p.parse_args(["abertura", "vigente", "--projeto", "x"]).func, cli_aberturas.cmd_vigente)
        for acao in (["preparar", "--projeto", "x", "--rascunho", "r.json"], ["verificar", "--projeto", "x"]):
            with self.subTest(acao=acao[0]):
                args = p.parse_args(["abertura", *acao])
                self.assertIs(args.func, principal.cmd_extensao)
                self.assertIs(args.executor, cli_aberturas.executar)

    def test_sem_abreviacao(self):
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            self.parser().parse_args(["abertura", "preparar", "--proj", "x", "--rascunho", "r.json"])

    def test_dest_acao_e_area_default_none_para_o_porteiro(self):
        """Pedido do PORTEIRO: a ação fica em `acao` (como os demais comandos), e --area tem default None (o padrão é
        resolvido no executor), para o aperto e o mapa tipado do porteiro conferirem contra o parser do kit."""
        p = self.parser()
        abertura = next(a for a in p._actions if isinstance(a, argparse._SubParsersAction)).choices["abertura"]
        sub = next(a for a in abertura._actions if isinstance(a, argparse._SubParsersAction))
        self.assertEqual(sub.dest, "acao")
        self.assertEqual(set(sub.choices), {"preparar", "verificar", "vigente"})
        for acao in ("preparar", "verificar", "vigente"):
            args = p.parse_args(["abertura", acao, "--projeto", "x", *(["--rascunho", "r"] if acao == "preparar" else [])])
            self.assertEqual(args.acao, acao)
        self.assertIsNone(p.parse_args(["abertura", "vigente", "--projeto", "x"]).area)


class TestPreparar(AberturasCliCase):
    def test_grava_a_ficha_canonica_numerada_e_mostra_o_comando_fixo(self):
        dados = rascunho(rede={"dominios": ["registry.npmjs.org"]})
        codigo, r = self.preparar(dados)
        self.assertEqual(codigo, 0, r)
        alvo = self.rascunhos / "ficha-v1.json"
        self.assertEqual(Path(r["arquivo"]), alvo.resolve())
        gravada = regras.carregar(alvo.read_bytes())
        self.assertEqual(alvo.read_bytes(), regras.canonico(gravada))
        self.assertEqual((gravada["versao"], gravada["ficha_id"], gravada["project_id"]),
                         (1, "aberturas-juridico-lab", "juridico-lab"))
        self.assertEqual([a["secao"] for a in r["aberturas"]], ["rede"])
        self.assertIn("canário", r["importante"])
        # A forma do bash aponta sempre para a cópia protegida do Ubuntu; a do PowerShell só sai com a cópia protegida
        # do Windows instalada e fora do alcance desta conta (revisão do pacote): sem ela, vem o motivo no lugar.
        self.assertIn("bash", r["para_o_titular"])
        if os.name == "nt":
            self.assertTrue({"executar_windows", "executar_windows_pendente"} & set(r["para_o_titular"]))
        for shell in sorted({"powershell", "bash"} & set(r["para_o_titular"])):
            with self.subTest(shell=shell):
                comando = r["para_o_titular"][shell]
                self.assertIn("fundacao_titular.py", comando)
                self.assertIn("assinar-ficha --raiz ", comando)
                self.assertTrue(comando.endswith(" --projeto juridico-lab --versao 1"), comando)
                for de_dentro_do_rascunho in ("registry", "npm", "Liberar"):
                    self.assertNotIn(de_dentro_do_rascunho, comando)
        self.assertEqual(events.count(self.con, "abertura_preparada", project_id="juridico-lab"), 1)
        codigo, r = self.preparar(dados)
        self.assertEqual((codigo, r["versao"]), (0, 2))

    def test_numera_depois_da_maior_vista_na_caixa_de_entrada(self):
        caixa = aberturas.caixa_de_entrada(self.root, "juridico-lab")
        caixa.mkdir(parents=True)
        (caixa / "ficha-v3.json").write_text("{}", encoding="ascii")
        codigo, r = self.preparar({**rascunho(), "versao": 1})
        self.assertEqual((codigo, r["versao"]), (0, 4), r)
        self.assertEqual(r["versao_do_rascunho_trocada"], {"no_rascunho": "1", "gravada": 4})

    def test_recusas_nao_gravam_nada(self):
        fora = self.root / "projects" / "reversa-lab" / "outputs" / "rascunho.json"
        fora.write_text(json.dumps(rascunho()), encoding="utf-8")
        casos = (("operador-juridico", rascunho(project_id="reversa-lab"), "E_VALIDATION"),
                 ("operador-juridico", rascunho(schema_version="fundacao.ficha_aberturas/9"), "E_VALIDATION"),
                 ("operador-juridico", rascunho(rede={"dominios": ["127.0.0.1", "*.vercel.app"]}), "E_VALIDATION"),
                 ("operador-juridico", rascunho(leitura_liberada=["src/secrets/chave.txt"]), "E_VALIDATION"),
                 ("operador-juridico", rascunho(motivo=""), "E_VALIDATION"),
                 ("operador-juridico", rascunho(vigencia_ate="2020-01-01"), "E_VALIDATION"),
                 ("operador-engenharia", rascunho(), "E_ACCESS_DENIED"))
        for quem, dados, codigo_erro in casos:
            with self.subTest(dados=sorted(dados), quem=quem):
                codigo, r = self.preparar(dados, quem=quem)
                self.assertEqual((codigo, r["error"]["code"]), (2, codigo_erro), r)
        codigo, r = self.cli("operador-juridico", "abertura", "preparar", "--projeto", "juridico-lab",
                             "--rascunho", str(fora))
        self.assertEqual((codigo, r["error"]["code"]), (2, "E_PATH_ESCAPE"))
        self.assertFalse(self.rascunhos.exists() and any(self.rascunhos.iterdir()))

    def test_erros_dos_tetos_vem_listados(self):
        codigo, r = self.preparar(rascunho(rede={"dominios": ["127.0.0.1"]}, webfetch={"dominios": ["docs.x.com.br"]},
                                           mcp=[{"nome": "y"}]))
        self.assertEqual(codigo, 2)
        campos = {e["campo"] for e in r["error"]["erros"]}
        self.assertTrue({"rede.dominios[0]", "webfetch.dominios", "mcp"} <= campos, campos)
        self.assertIn("1.7.11", json.dumps(r, ensure_ascii=False))

    def test_rascunho_ilegivel_ou_inexistente(self):
        (self.pasta / "outputs" / "ruim.json").write_text('{"motivo": "a", "motivo": "b"}', encoding="utf-8")
        for nome, codigo_erro in (("ruim.json", "E_VALIDATION"), ("nao-existe.json", "E_NOT_FOUND")):
            with self.subTest(nome=nome):
                codigo, r = self.cli("operador-juridico", "abertura", "preparar", "--projeto", "juridico-lab",
                                     "--rascunho", f"outputs/{nome}")
                self.assertEqual((codigo, r["error"]["code"]), (2, codigo_erro))

    def test_plugin_tem_o_manifesto_calculado_e_plugin_com_hooks_recusa(self):
        plugin = self.pasta / "plugins-candidatos" / "juridico-lab-modelos"
        (plugin / ".claude-plugin").mkdir(parents=True)
        (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "juridico-lab-modelos"}),
                                                               encoding="utf-8")
        (plugin / "commands").mkdir()
        (plugin / "commands" / "resumo.md").write_text("Resuma o caso fictício.\n", encoding="utf-8")
        item = {"nome": "juridico-lab-modelos", "origem": "plugins-candidatos/juridico-lab-modelos",
                "manifesto_sha256": ""}
        codigo, r = self.preparar(rascunho(plugins=[item]))
        self.assertEqual(codigo, 0, r)
        gravada = regras.carregar(Path(r["arquivo"]).read_bytes())
        self.assertRegex(gravada["plugins"][0]["manifesto_sha256"], r"^[0-9a-f]{64}$")
        (plugin / "hooks").mkdir()
        codigo, r = self.preparar(rascunho(plugins=[item]))
        self.assertEqual(codigo, 2)
        self.assertIn("1.7.11", json.dumps(r["error"]["erros"], ensure_ascii=False))

    def test_trava_de_outro_projeto_recusa(self):
        codigo, r = self.preparar(ambiente={cli_aberturas.ENV_TRAVA: "reversa-lab"})
        self.assertEqual((codigo, r["error"]["code"]), (2, "E_ACCESS_DENIED"))


class TestPrepararSemLigacao(AberturasCliCase):
    """Gravação e leitura do preparar sem seguir ligação (revisão do pacote: faltavam os testes negativos)."""

    def setUp(self):
        super().setUp()
        self.fora = self.root.parent / (self.root.name + "-fora")
        self.fora.mkdir()
        self.addCleanup(shutil.rmtree, self.fora, ignore_errors=True)

    def test_outputs_aberturas_ligada_recusa_e_nada_vai_para_o_outro_lado(self):
        (self.pasta / "outputs").mkdir(exist_ok=True)
        ligar_pasta(self, self.rascunhos, self.fora)
        codigo, r = self.preparar()
        self.assertEqual((codigo, r["error"]["code"]), (2, "E_PATH_ESCAPE"), r)
        self.assertEqual(list(self.fora.iterdir()), [])

    def test_outputs_ligada_recusa_ao_ler_o_rascunho(self):
        shutil.rmtree(self.pasta / "outputs", ignore_errors=True)
        ligar_pasta(self, self.pasta / "outputs", self.fora)
        (self.fora / "rascunho.json").write_text(json.dumps(rascunho()), encoding="utf-8")
        codigo, r = self.cli("operador-juridico", "abertura", "preparar", "--projeto", "juridico-lab", "--rascunho",
                             "outputs/rascunho.json")
        self.assertEqual((codigo, r["error"]["code"]), (2, "E_PATH_ESCAPE"), r)
        self.assertEqual(sorted(p.name for p in self.fora.iterdir()), ["rascunho.json"])

    def test_rascunho_lido_por_pasta_ligada_a_outro_projeto_recusa(self):
        outro = self.root / "projects" / "reversa-lab" / "outputs"
        outro.mkdir(parents=True, exist_ok=True)
        (outro / "rascunho.json").write_text(json.dumps(rascunho(motivo="Texto do outro projeto (fictício).")),
                                             encoding="utf-8")
        (self.pasta / "outputs").mkdir(exist_ok=True)
        ligar_pasta(self, self.pasta / "outputs" / "ligada", outro)
        codigo, r = self.cli("operador-juridico", "abertura", "preparar", "--projeto", "juridico-lab", "--rascunho",
                             "outputs/ligada/rascunho.json")
        self.assertEqual((codigo, r["error"]["code"]), (2, "E_PATH_ESCAPE"), r)
        self.assertNotIn("outro projeto", json.dumps(r, ensure_ascii=False))
        self.assertFalse(self.rascunhos.exists() and any(self.rascunhos.iterdir()))


class TestComandoNaCopiaProtegida(AberturasCliCase):
    """O comando fixo do titular aponta para a cópia protegida da ferramenta (revisão do pacote, 31/10/2026)."""

    def instalar(self, python: str = r"C:\Program Files\Python312\python.exe") -> Path:
        base = self.root.parent / (self.root.name + "-programdata")
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        (base / KIT_VERSION).mkdir(parents=True, exist_ok=True)
        (base / KIT_VERSION / "hashes.json").write_text(json.dumps(
            {"schema_version": aberturas.ESQUEMA_HASHES, "versao": KIT_VERSION, "arquivos": {},
             "python": {"caminho": python, "sha256": "0" * 64}}), encoding="utf-8")
        padrao = mock.patch.object(aberturas_comando, "FERRAMENTA_WINDOWS", str(base))
        padrao.start()
        self.addCleanup(padrao.stop)
        # A cópia instalada inteira: com o Python fixado que esta conta não altera e com o SHA-256 registrado (item
        # I13 da integração). A conferência do Python tem testes próprios (test_aberturas_comando_i13.py).
        python_fixado = mock.patch.object(aberturas_comando, "conferir_python", return_value=None)
        python_fixado.start()
        self.addCleanup(python_fixado.stop)
        return base

    def test_python_da_copia_windows(self):
        self.instalar()
        with mock.patch.object(decisoes, "conferir_ancora", return_value={"protegida": True}):
            self.assertEqual(aberturas.python_da_copia_windows(), (r"C:\Program Files\Python312\python.exe", ""))
        with mock.patch.object(decisoes, "conferir_ancora", return_value={"protegida": False, "motivo": "ADD_FILE"}):
            python, motivo = aberturas.python_da_copia_windows()
        self.assertIsNone(python)
        self.assertIn("não está protegida", motivo)
        for ruim in (r"C:\Python\python.exe; iex (iwr x)", r"C:\a;b\python.exe", "python.exe", r"C:\x\outro.exe",
                     "C:\\x\\'\\python.exe"):
            with self.subTest(python=ruim):
                self.instalar(ruim)
                with mock.patch.object(decisoes, "conferir_ancora", return_value={"protegida": True}):
                    self.assertIsNone(aberturas.python_da_copia_windows()[0])
        with mock.patch.object(aberturas_comando, "FERRAMENTA_WINDOWS", str(self.root / "nao-instalada")):
            self.assertIn("ainda não foi instalada", aberturas.python_da_copia_windows()[1])

    @unittest.skipUnless(os.name == "nt", "a forma do PowerShell só é montada no Windows")
    def test_forma_do_powershell_com_o_python_fixado(self):
        base = self.instalar()
        with mock.patch.object(decisoes, "conferir_ancora", return_value={"protegida": True}):
            r = aberturas.comando_do_titular(self.root, "juridico-lab", 3)
        comando = r["powershell"]
        self.assertTrue(comando.startswith(r"& 'C:\Program Files\Python312\python.exe' -I -B -S '"), comando)
        self.assertIn(str(base / KIT_VERSION / "assets" / "host" / "fundacao_titular.py"), comando)
        self.assertTrue(comando.endswith(" --projeto juridico-lab --versao 3"), comando)
        self.assertNotIn("USERPROFILE", comando)

    def test_forma_do_bash_na_copia_protegida_do_ubuntu(self):
        r = aberturas.comando_do_titular(self.root, "juridico-lab", 2)
        self.assertTrue(r["bash"].startswith(f"/usr/bin/python3 -I -B -S '/usr/local/lib/fundacao-ia/{KIT_VERSION}/"
                                             "assets/host/fundacao_titular.py' assinar-ficha --raiz '"), r["bash"])
        self.assertNotIn("$HOME", r["bash"])

    def test_aviso_manda_nao_colar_em_shell_aberto_e_usar_win_r(self):
        with mock.patch.object(aberturas_comando, "_copia_posix_vista", return_value=True):  # cópia do Ubuntu à vista
            r = aberturas.comando_do_titular(self.root, "juridico-lab", 1)  # (sem ela: test_aberturas_comando_i13.py)
        if os.name == "nt" or aberturas_comando.em_wsl():  # onde há caixa Executar (reconferência de 01/11/2026)
            self.assertIn("NÃO cole num PowerShell ou bash já aberto", r["aviso"])
            self.assertIn("Win+R", r["onde_rodar"])
        else:  # num Linux fora do WSL não há caixa Executar: nem o aviso nem o passo a citam
            self.assertNotIn("Win+R", r["aviso"] + r["onde_rodar"])
            self.assertIn("'bash'", r["onde_rodar"])

    @unittest.skipUnless(os.name == "nt", "a caixa Executar (Win+R) e o wsl.exe são do Windows")
    def test_formas_executar_abrem_processo_direto_sem_shell(self):
        """Revisão do pacote (31/10/2026): o shell novo sem perfil. 'executar_windows' abre o python.exe direto (sem
        PowerShell); 'executar_ubuntu' abre o wsl.exe (caminho absoluto do sistema) -e python3 direto (sem bash)."""
        base = self.instalar()
        with mock.patch.object(decisoes, "conferir_ancora", return_value={"protegida": True}), \
                mock.patch.object(aberturas_comando, "CAIXA_EXECUTAR", 10_000):  # a forma, não o limite (outro teste)
            r = aberturas.comando_do_titular(self.root, "juridico-lab", 3)
        win = r["executar_windows"]
        self.assertTrue(win.startswith('"C:\\Program Files\\Python312\\python.exe" -I -B -S "'), win)
        self.assertIn(str(base / KIT_VERSION / "assets" / "host" / "fundacao_titular.py"), win)
        self.assertNotIn("powershell", win.lower())
        self.assertTrue(win.endswith(" --projeto juridico-lab --versao 3"), win)
        ub = r["executar_ubuntu"]
        wsl = os.path.join(os.environ["SystemRoot"], "System32", "wsl.exe")
        self.assertTrue(ub.startswith(f'"{wsl}" -e /usr/bin/python3 -I -B -S '), ub)
        self.assertIn(f"/usr/local/lib/fundacao-ia/{KIT_VERSION}/assets/host/fundacao_titular.py", ub)
        for comando in (win, ub):
            for de_dentro in ("registry", "npm", "Liberar", ";", "|", "iex"):
                self.assertNotIn(de_dentro, comando)

    @unittest.skipUnless(os.name == "nt", "o ambiente sem SystemRoot só interessa no Windows")
    def test_executar_ubuntu_pendente_sem_system_root(self):
        self.instalar()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SystemRoot", None)
            os.environ.pop("windir", None)
            with mock.patch.object(decisoes, "conferir_ancora", return_value={"protegida": True}):
                r = aberturas.comando_do_titular(self.root, "juridico-lab", 3)
        self.assertNotIn("executar_ubuntu", r)
        self.assertIn("executar_ubuntu_pendente", r)


def citadas(r: dict) -> set[str]:
    """As chaves que o onde_rodar manda usar (entre aspas simples)."""
    return set(re.findall(r"'([a-z_]+)'", r["onde_rodar"]))


class TestComandoNoWslENoLinux(AberturasCliCase):
    """Reconferência do pacote (01/11/2026): o fluxo do Ubuntu é o principal da 1.7.10 (o kit roda no Linux, pelo
    porteiro, com `env -i` e o WSL_DISTRO_NAME da emenda E1). Antes, no Linux só saía a forma `bash`, colada num
    terminal cujo ~/.bashrc a sessão com a raiz em /mnt/e consegue gravar, e o onde_rodar mandava colar
    'executar_windows' ou 'executar_ubuntu', que não saíam. Raízes fictícias (/mnt/d/IA/fundacao, /srv/fundacao)."""

    instalar = TestComandoNaCopiaProtegida.instalar

    def ambiente_wsl(self, distro: str | None = "Ubuntu", copia_do_ubuntu: bool = True) -> None:
        """O ambiente do kit no porteiro: sem SystemRoot nem windir (o WSL não os herda) e com WSL_DISTRO_NAME. Sem a
        variável, o WSL é dado como detectado pelo /proc/version (simulado: a CI do Linux não é WSL). A cópia protegida
        do Ubuntu é dada como à vista (a CI e esta máquina não a têm; o onde_rodar depende dela desde o item I13 da
        integração); sem ela, os testes de test_aberturas_comando_i13.py."""
        ambiente = mock.patch.dict(os.environ, {}, clear=False)
        ambiente.start()
        self.addCleanup(ambiente.stop)
        for nome in ("SystemRoot", "windir", "WSL_DISTRO_NAME"):
            os.environ.pop(nome, None)
        sem_copia = mock.patch.object(aberturas_comando, "FERRAMENTA_WINDOWS", str(self.root / "sem-copia-windows"))
        sem_copia.start()  # nada do /mnt/c desta máquina é lido; quem precisa da cópia chama instalar()
        self.addCleanup(sem_copia.stop)
        if copia_do_ubuntu:
            vista = mock.patch.object(aberturas_comando, "_copia_posix_vista", return_value=True)
            vista.start()
            self.addCleanup(vista.stop)
        if distro is None:
            wsl = mock.patch.object(aberturas_comando, "em_wsl", return_value=True)
            wsl.start()
            self.addCleanup(wsl.stop)
        else:
            os.environ["WSL_DISTRO_NAME"] = distro

    def assert_onde_rodar_coerente(self, r: dict) -> None:
        self.assertTrue(citadas(r), r["onde_rodar"])
        self.assertEqual(citadas(r) - set(r), set(), r["onde_rodar"])  # nada citado que não saiu

    @unittest.skipUnless(os.name == "posix", "o kit no Linux do WSL (o fluxo do porteiro)")
    def test_no_wsl_executar_ubuntu_pela_caixa_com_a_distribuicao(self):
        self.ambiente_wsl()
        r = aberturas.comando_do_titular("/mnt/d/IA/fundacao", "juridico-lab", 3)
        ub = r["executar_ubuntu"]
        self.assertTrue(ub.startswith('"C:\\Windows\\System32\\wsl.exe" -d Ubuntu -e /usr/bin/python3 -I -B -S '
                                      '"/usr/local/lib/fundacao-ia/'), ub)
        self.assertIn(f'"/usr/local/lib/fundacao-ia/{KIT_VERSION}/assets/host/fundacao_titular.py"', ub)
        self.assertTrue(ub.endswith(' assinar-ficha --raiz "/mnt/d/IA/fundacao" --projeto juridico-lab --versao 3'), ub)
        self.assertLessEqual(len(ub), aberturas_comando.CAIXA_EXECUTAR)
        self.assertIn("Win+R", r["onde_rodar"])
        self.assert_onde_rodar_coerente(r)

    @unittest.skipUnless(os.name == "posix", "o kit no Linux do WSL (o fluxo do porteiro)")
    def test_no_wsl_a_forma_do_windows_pela_copia_protegida_vista_em_mnt_c(self):
        """A chave e a âncora do titular ficam no Windows (comando_titular.shell_padrao): no WSL saem também as formas
        do Windows, com a cópia protegida conferida pelo caminho visto do WSL (aqui, uma pasta temporária)."""
        self.ambiente_wsl()
        self.instalar()
        with mock.patch.object(decisoes, "conferir_ancora", return_value={"protegida": True}) as sonda:
            r = aberturas.comando_do_titular("/mnt/d/IA/fundacao", "juridico-lab", 3)
        self.assertEqual(sonda.call_count, 1)
        win = r["executar_windows"]
        self.assertTrue(win.startswith('"C:\\Program Files\\Python312\\python.exe" -I -B -S "'), win)
        self.assertTrue(win.endswith(' assinar-ficha --raiz "D:\\IA\\fundacao" --projeto juridico-lab --versao 3'), win)
        self.assertIn("--raiz 'D:\\IA\\fundacao' --projeto", r["powershell"])
        self.assertTrue(r["onde_rodar"].startswith("FORA do Claude: tecle Win+R"), r["onde_rodar"])
        self.assertIn("'executar_windows'", r["onde_rodar"])
        self.assert_onde_rodar_coerente(r)
        with mock.patch.object(decisoes, "conferir_ancora", return_value={"protegida": False, "motivo": "abrir"}):
            r = aberturas.comando_do_titular("/mnt/d/IA/fundacao", "juridico-lab", 3)
        self.assertNotIn("executar_windows", r)
        self.assertIn("não está protegida", r["executar_windows_pendente"])

    @unittest.skipUnless(os.name == "posix", "o kit no Linux do WSL (o fluxo do porteiro)")
    def test_no_wsl_sem_a_copia_do_windows_o_onde_rodar_so_cita_o_que_saiu(self):
        self.ambiente_wsl(None)
        with mock.patch.object(aberturas_comando, "FERRAMENTA_WINDOWS", str(self.root / "nao-instalada")):
            r = aberturas.comando_do_titular("/mnt/d/IA/fundacao", "juridico-lab", 3)
        self.assertFalse({"executar_windows", "powershell"} & set(r))
        self.assertIn("ainda não foi instalada", r["executar_windows_pendente"])
        self.assertTrue(r["executar_ubuntu"].startswith('"C:\\Windows\\System32\\wsl.exe" -e /usr/bin/python3 '))
        self.assertIn("'executar_ubuntu'", r["onde_rodar"])
        self.assertIn("'executar_windows_pendente'", r["onde_rodar"])
        self.assert_onde_rodar_coerente(r)

    @unittest.skipUnless(os.name == "posix", "o kit no Linux")
    def test_linux_fora_do_wsl_so_a_forma_bash_e_sem_win_r(self):
        ambiente = mock.patch.dict(os.environ, {}, clear=False)
        ambiente.start()
        self.addCleanup(ambiente.stop)
        os.environ.pop("WSL_DISTRO_NAME", None)
        with mock.patch.object(aberturas_comando, "em_wsl", return_value=False), \
                mock.patch.object(aberturas_comando, "_copia_posix_vista", return_value=True):  # cópia à vista (I13)
            r = aberturas.comando_do_titular("/srv/fundacao", "juridico-lab", 3)
        self.assertEqual({c for c in r if not c.endswith("_pendente")}, {"bash", "onde_rodar", "aviso"})
        self.assertNotIn("Win+R", r["onde_rodar"] + r["aviso"])
        self.assertNotIn("Executar (", r["onde_rodar"])
        self.assertIn("'bash'", r["onde_rodar"])
        self.assertIn("~/.bashrc", r["aviso"])
        self.assert_onde_rodar_coerente(r)

    @unittest.skipUnless(os.name == "posix", "o kit no Linux do WSL (o fluxo do porteiro)")
    def test_distribuicao_fora_da_forma_nao_entra_no_comando(self):
        for distro in ("Ubuntu; rm -rf /", "Ubuntu 24.04", "Ubuntu\n", "-e", "--exec"):
            with self.subTest(distro=distro):
                self.ambiente_wsl(distro)
                r = aberturas.comando_do_titular("/mnt/d/IA/fundacao", "juridico-lab", 3)
                self.assertTrue(r["executar_ubuntu"].startswith('"C:\\Windows\\System32\\wsl.exe" -e '), r)
                self.assertNotIn(" -d ", r["executar_ubuntu"])
                self.assertNotIn("rm -rf", json.dumps(r))
        self.ambiente_wsl("Ubuntu-24.04")
        r = aberturas.comando_do_titular("/mnt/d/IA/fundacao", "juridico-lab", 1)
        self.assertIn(" -d Ubuntu-24.04 -e ", r["executar_ubuntu"])

    def test_raiz_que_a_caixa_executar_nao_passa_inteira_fica_pendente(self):
        """'%' (a caixa Executar expande %VAR%), barra invertida no fim e comando acima de 259 caracteres (o limite
        da caixa): a forma da caixa não sai, o motivo sai, e o último recurso continua."""
        if os.name == "posix":
            self.ambiente_wsl()
        elif not os.environ.get("SystemRoot"):
            self.skipTest("sem SystemRoot no ambiente do Windows")
        else:  # nada do C:\ProgramData desta máquina entra no ensaio
            sem_copia = mock.patch.object(aberturas_comando, "FERRAMENTA_WINDOWS", str(self.root / "sem-copia-windows"))
            sem_copia.start()
            self.addCleanup(sem_copia.stop)
        longa = "/mnt/d/" + "/".join(["pasta-ficticia-de-nome-longo"] * 7)
        for raiz, trecho in (("/mnt/d/IA/100%fundacao", "'%'"), (longa, str(aberturas_comando.CAIXA_EXECUTAR))):
            with self.subTest(raiz=raiz[:24]):
                r = aberturas.comando_do_titular(raiz, "juridico-lab", 3)
                self.assertNotIn("executar_ubuntu", r)
                self.assertIn(trecho, r["executar_ubuntu_pendente"])
                self.assertIn("bash", r)
                self.assert_onde_rodar_coerente(r)
        self.assertIsNone(aberturas_comando._aspas_run("D:\\"))
        self.assertEqual(aberturas_comando._aspas_run("D:\\IA"), '"D:\\IA"')

    @unittest.skipUnless(os.name == "nt", "a sessão do Windows")
    def test_no_windows_o_onde_rodar_so_cita_o_que_saiu(self):
        self.instalar()
        limite = mock.patch.object(aberturas_comando, "CAIXA_EXECUTAR", 10_000)  # a pasta temporária é longa
        limite.start()
        self.addCleanup(limite.stop)
        for protegida in (True, False):
            sondagem = {"protegida": protegida, "motivo": "ADD_FILE"}
            with self.subTest(protegida=protegida), mock.patch.object(decisoes, "conferir_ancora", return_value=sondagem):
                r = aberturas.comando_do_titular(self.root, "juridico-lab", 3)
                self.assertEqual("executar_windows" in r, protegida)
                self.assertEqual("executar_windows_pendente" in r, not protegida)
                self.assert_onde_rodar_coerente(r)


class TestVerificarEVigente(AberturasCliCase):
    def assinar_na_caixa(self, versao: int = 1) -> Path:
        caixa = aberturas.caixa_de_entrada(self.root, "juridico-lab")
        caixa.mkdir(parents=True, exist_ok=True)
        alvo = caixa / f"ficha-v{versao}.json"
        alvo.write_bytes((self.rascunhos / f"ficha-v{versao}.json").read_bytes())
        self.assinador.assinar(alvo)
        return alvo

    def test_verificar_antes_e_depois_da_assinatura(self):
        self.assertEqual(self.preparar(rascunho(rede={"dominios": ["pypi.org"]}))[0], 0)
        codigo, r = self.cli("operador-juridico", "abertura", "verificar", "--projeto", "juridico-lab")
        self.assertEqual(codigo, 0, r)
        self.assertEqual((r["versao"], r["valida"], r["forma_canonica"], r["erros"]), (1, True, True, []))
        self.assertFalse(r["assinatura"]["na_caixa_de_entrada"])
        self.assinar_na_caixa()
        r = self.cli("operador-juridico", "abertura", "verificar", "--projeto", "juridico-lab", "--versao", "1")[1]
        self.assertEqual((r["assinatura"]["valida"], r["assinatura"]["igual_a_esta"]), (True, True))

    def test_verificar_acusa_a_ficha_alterada_depois_do_preparo(self):
        self.assertEqual(self.preparar()[0], 0)
        alvo = self.rascunhos / "ficha-v1.json"
        alterada = {**regras.carregar(alvo.read_bytes()), "rede": {"dominios": ["*.github.io"]}}
        alvo.write_text(json.dumps(alterada), encoding="utf-8")
        r = self.cli("operador-juridico", "abertura", "verificar", "--projeto", "juridico-lab")[1]
        self.assertFalse(r["valida"])
        self.assertEqual([e["campo"] for e in r["erros"]], ["rede.dominios[0]"])
        codigo, r = self.cli("operador-engenharia", "abertura", "verificar", "--projeto", "juridico-lab")
        self.assertEqual((codigo, r["error"]["code"]), (2, "E_ACCESS_DENIED"))

    def test_verificar_ficha_adulterada_com_tipos_errados_responde_invalida(self):
        """Antes, `dominios` que não era lista levantava TypeError fora do formato de erro (revisão do pacote)."""
        self.assertEqual(self.preparar(rascunho(rede={"dominios": ["pypi.org"]}))[0], 0)
        alvo = self.rascunhos / "ficha-v1.json"
        original = regras.carregar(alvo.read_bytes())
        for adulterada in ({"rede": {"dominios": 5}}, {"rede": {"dominios": "abc"}}, {"webfetch": {"dominios": 7}},
                           {"plugins": 5}, {"plugins": "abc"}, {"rede": ["pypi.org"]}):
            with self.subTest(adulterada=adulterada):
                alvo.write_text(json.dumps({**original, **adulterada}), encoding="utf-8")
                codigo, r = self.cli("operador-juridico", "abertura", "verificar", "--projeto", "juridico-lab")
                self.assertEqual(codigo, 0, r)
                self.assertFalse(r["valida"])
                self.assertIn(next(iter(adulterada)), {e["campo"] for e in r["erros"]})
                self.assertNotIn(next(iter(adulterada)), {a["secao"] for a in r["aberturas"]})  # nada adulterado abre

    def test_vigente_sem_banco_e_sem_identidade(self):
        self.assertEqual(self.preparar()[0], 0)
        self.assinar_na_caixa()
        caixa = aberturas.caixa_de_entrada(self.root, "juridico-lab")
        with mock.patch.object(principal, "_con", side_effect=AssertionError("vigente abriu o banco")):
            codigo, r = self.cli(None, "abertura", "vigente", "--projeto", "juridico-lab", "--area", str(caixa),
                                 "--json")
        self.assertEqual(codigo, 0, r)
        self.assertEqual((r["valida"], r["versao"], r["area"]), (True, 1, str(caixa)))

    def test_vigente_na_area_padrao(self):
        codigo, r = self.cli(None, "abertura", "vigente", "--projeto", "juridico-lab")
        self.assertEqual(codigo, 0)
        self.assertFalse(r["valida"])
        if os.name == "nt":
            self.assertEqual(r["area"], "caixa-de-entrada (não instalada)")
        else:
            self.assertEqual(r["area"], "/etc/fundacao-ia/projetos/juridico-lab/ficha")

    def test_vigente_com_a_trava(self):
        trava = {cli_aberturas.ENV_TRAVA: "juridico-lab"}
        self.assertEqual(self.cli(None, "abertura", "vigente", "--projeto", "juridico-lab", ambiente=trava)[0], 0)
        recusas = ((["--projeto", "reversa-lab"], trava),
                   (["--projeto", "juridico-lab", "--area", str(self.root)], trava),
                   (["--projeto", "juridico-lab"], {**trava, cli_aberturas.ENV_RAIZ: str(self.root / "outra")}))
        for argv, ambiente in recusas:
            with self.subTest(argv=argv):
                codigo, r = self.cli(None, "abertura", "vigente", *argv, ambiente=ambiente)
                self.assertEqual((codigo, r["error"]["code"]), (2, "E_ACCESS_DENIED"))

    def test_executar_direto_sem_banco_so_vigente(self):
        args = argparse.Namespace(acao="preparar", projeto="juridico-lab", raiz=self.root, rascunho=Path("x"))
        with mock.patch.dict(os.environ, {}):
            os.environ.pop(cli_aberturas.ENV_TRAVA, None)
            with self.assertRaises(FundacaoError):
                cli_aberturas.executar(args)
            args = argparse.Namespace(acao="vigente", projeto="juridico-lab", raiz=self.root,
                                      area=self.root / "nada")
            self.assertFalse(cli_aberturas.executar(args)["valida"])
