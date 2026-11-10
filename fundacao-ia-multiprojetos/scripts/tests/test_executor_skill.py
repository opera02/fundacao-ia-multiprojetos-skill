"""1.7.11, lote S3 (desenho de skills e agentes, §3.3, §3.4 e §5): o executor das skills com scripts.

O que o lote muda (`assets/host/wsl/executor_skill.py`, o lançador `fundacao-skill-<p>` gerado pelo preparo e o
`conferir-abertura`), com a prova negativa de cada ponto:
- só roda script listado na ficha aplicada, pelo NOME (não por caminho), com o SHA-256 da ficha na cópia root (N-SK-2,
  N-HASH-2); o modo `caixa` (S4) fica fechado, com a mensagem;
- antes de cada execução reconfere o interpretador e a árvore da venv contra o hashes.json, pelas funções do preparo
  (N-HASH-4); a pasta atual e a variável de projeto travam o projeto (N-SK-4, lógica);
- o argumento do script nunca vira opção do Python; o ambiente é o mínimo; cada execução deixa duas linhas no registro,
  e sem o registro o script não roda;
- o `conferir-abertura` reconfere a venv e o lançador do executor, e o lançador confere o executor pelo SHA-256.
U roda nos dois sistemas (script e interpretador de ensaio, `rodar` trocado). L roda só no Ubuntu (Python do sistema, venv
e rodas de teste geradas aqui, o lançador de verdade) e pula nos outros com o motivo. Dados fictícios; nenhum código de
terceiros roda.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
import uuid
from pathlib import Path

from apoio import SKILL
from test_host_projeto_apoio import LINUX, carregar_preparo, ficha_de_ensaio, gravar_ficha_na_caixa, usuario_atual
from test_host_projeto_skills import (CHAVE, PLUGIN, PROJETO, RODAS_REL, SCRIPT, SCRIPT_REL, PipFalso,
                                      _caso_de_instalacao, _instalar_cli, _vigente_de_ensaio, escrever, gerar_roda,
                                      montar_plugin)

EXECUTOR = SKILL / "assets" / "host" / "wsl" / "executor_skill.py"
LOCK = "a1" * 32
VENV_REL = f"{PROJETO}/{PLUGIN}/{LOCK[:12]}/venv"
HOME_FALSO = {"LANG": "C.UTF-8", "HTTPS_PROXY": "http://localhost:3128", "NO_PROXY": "localhost", "https_proxy": "http://localhost:3128",
              "SEGREDO_TOKEN": "x", "PYTHONPATH": "/tmp/fora", "PYTHONSTARTUP": "/tmp/fora.py", "LD_PRELOAD": "/tmp/fora.so",
              "BASH_ENV": "/tmp/fora.sh", "FUNDACAO_PORTEIRO": "/tmp/p", "SSH_AUTH_SOCK": "/tmp/s", "PYTHONHOME": "/tmp/h"}


def carregar_executor():
    """Uma cópia nova do módulo (o cache de módulos carregados é por cópia)."""
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("executor_skill_s3_" + uuid.uuid4().hex[:8], EXECUTOR)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class Rodar:
    """O `executor.rodar` de unidade: registra a chamada e devolve o código combinado."""

    def __init__(self, codigo: int = 0):
        self.chamadas, self.codigo = [], codigo

    def __call__(self, argv, env, cwd):
        self.chamadas.append({"argv": list(argv), "env": dict(env), "cwd": cwd})
        return self.codigo


class Cenario(unittest.TestCase):
    """Uma área root de ensaio (aberturas.json, hashes.json, cópia dos scripts e uma venv de mentira) e o executor com
    o interpretador de ensaio. O executor carrega o `preparo_skills.py` e o `copia_segura.py` DESTA skill."""

    def setUp(self):
        self.ex = carregar_executor()
        self.tmp = Path(tempfile.mkdtemp(prefix="executor-s3-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.raiz, self.skills = self.tmp / "Raiz de Ensaio", self.tmp / "skills"
        self.proj = self.raiz / "projects" / PROJETO
        self.proj.mkdir(parents=True)
        (self.raiz / "projects" / "lab-a").mkdir()
        self.area = self.tmp / "area" / "projetos" / PROJETO
        self.python = self.tmp / "bin-falso" / "python3.12"
        escrever(self.python.parent, "python3.12", "interpretador de ensaio\n")
        self.ps = self.ex.preparo_skills()
        patch = unittest.mock.patch.object(self.ps, "PYTHON", str(self.python))
        patch.start()
        self.addCleanup(patch.stop)
        self.rodar = Rodar()
        patch = unittest.mock.patch.object(self.ex, "rodar", self.rodar)
        patch.start()
        self.addCleanup(patch.stop)
        self.home = self.tmp / "home"
        self.ambiente = {**HOME_FALSO, "HOME": str(self.home), "TMPDIR": str(self.tmp / "tmp"), "FUNDACAO_PROJECT": PROJETO}
        self.venv = self.skills / VENV_REL
        escrever(self.venv, "pyvenv.cfg", "home = /usr/bin\n")
        escrever(self.venv, "bin/python", "binario de ensaio\n")
        escrever(self.venv, "lib/python3.12/site-packages/ensaio_um/__init__.py", "VALOR = 'um'\n")
        self.script = self.area / "plugins" / PLUGIN / SCRIPT_REL
        escrever(self.area / "plugins" / PLUGIN, SCRIPT_REL, SCRIPT)
        self.ficha = self.ficha_de(modo="sessao")
        self.hashes = self.hashes_de()
        self.gravar()

    def ficha_de(self, modo: str, com_pacotes: bool = True) -> dict:
        skill = {"skill": "busca", "skill_md_sha256": "b" * 64, "scripts": [
            {"nome": "buscar", "caminho": SCRIPT_REL, "sha256": hashlib.sha256(SCRIPT.encode("utf-8")).hexdigest(),
             "modo": modo}]}
        if com_pacotes:
            skill["dependencias"] = {"lock": "skills/busca/requirements.lock", "lock_sha256": LOCK, "rodas": RODAS_REL,
                                     "python": "3.12", "pacotes": 1}
        return {"projeto": PROJETO, "valida": True,
                "plugins": [{"nome": PLUGIN, "manifesto_sha256": "c" * 64, "skills_com_scripts": [skill]}]}

    def hashes_de(self, com_pacotes: bool = True) -> dict:
        soma = self.ps.sha256_da_venv(self.ps.arvore_da_venv(self.venv))
        venv = ({"caminho": self.venv.as_posix(), "sha256": soma, "lock_sha256": LOCK} if com_pacotes else None)
        inter = {"caminho": os.path.realpath(self.python), "sha256": hashlib.sha256(self.python.read_bytes()).hexdigest(),
                 "versao": "3.12"}
        return {"projeto": PROJETO, "raiz": self.raiz.as_posix(), "skills": {CHAVE: {"interpretador": inter, "venv": venv}}}

    def gravar(self) -> None:
        self.area.mkdir(parents=True, exist_ok=True)
        for nome, dados in (("aberturas.json", self.ficha), ("hashes.json", self.hashes)):
            (self.area / nome).write_text(json.dumps(dados), encoding="utf-8", newline="\n")

    def executar(self, *cli, ambiente=None, cwd=None, opcoes=None) -> tuple[int, str]:
        """(código, stderr) do executor com o que o lançador monta antes do `--`."""
        opcoes = opcoes if opcoes is not None else ["--projeto", PROJETO, "--area", str(self.area), "--skills-base", str(self.skills)]
        erro = io.StringIO()
        with contextlib.redirect_stderr(erro):
            codigo = self.ex.executar([*opcoes, "--", *cli], self.ambiente if ambiente is None else ambiente,
                                      str(cwd or self.proj))
        return codigo, erro.getvalue()

    def registro(self) -> list[dict]:
        arquivo = self.proj / "outputs" / "skills" / "registro.jsonl"
        return [json.loads(l) for l in arquivo.read_text(encoding="utf-8").splitlines()] if arquivo.exists() else []

    def nada_rodou(self, codigo: int, erro: str, trecho: str = "") -> None:
        self.assertEqual(codigo, 2, erro)
        self.assertEqual(self.rodar.chamadas, [])
        self.assertEqual(self.registro(), [])
        self.assertIn("recusado, nada rodou", erro)
        self.assertIn(trecho, erro)


class RodaOQueAFichaLista(Cenario):
    def test_roda_pelo_nome_com_o_python_da_venv_e_deixa_o_registro(self):
        self.rodar.codigo = 3
        codigo, erro = self.executar(CHAVE, "buscar", "--", "um", "dois")
        self.assertEqual((codigo, erro), (3, ""))
        (chamada,) = self.rodar.chamadas
        self.assertEqual(chamada["argv"], [(self.venv / "bin" / "python").as_posix(), "-I", "-B", self.script.as_posix(),
                                           "um", "dois"])
        self.assertEqual(chamada["cwd"], str(self.proj))
        inicio, fim = self.registro()
        self.assertEqual((inicio["fase"], fim["fase"]), ("inicio", "fim"))
        for linha in (inicio, fim):
            self.assertEqual((linha["plugin"], linha["skill"], linha["script"], linha["argv"], linha["argc"]),
                             (PLUGIN, "busca", "buscar", ["um", "dois"], 2))
            self.assertEqual(linha["sha256"], hashlib.sha256(SCRIPT.encode("utf-8")).hexdigest())
        self.assertEqual(fim["codigo"], 3)
        self.assertIn("conferencia_s", inicio)
        self.assertIn("duracao_s", fim)

    def test_sem_pacotes_roda_com_o_interpretador_do_hashes(self):
        self.ficha, self.hashes = self.ficha_de("sessao", com_pacotes=False), self.hashes_de(com_pacotes=False)
        self.gravar()
        self.assertEqual(self.executar(CHAVE, "buscar")[0], 0)
        self.assertEqual(self.rodar.chamadas[0]["argv"][:4], [os.path.realpath(self.python), "-I", "-B", self.script.as_posix()])

    def test_o_ambiente_e_o_minimo(self):
        self.executar(CHAVE, "buscar")
        env = self.rodar.chamadas[0]["env"]
        self.assertEqual(env, {"PATH": "/usr/bin:/bin", "FUNDACAO_PROJECT": PROJETO, "LANG": "C.UTF-8",
                               "HOME": str(self.home), "TMPDIR": str(self.tmp / "tmp"),
                               "HTTPS_PROXY": "http://localhost:3128", "NO_PROXY": "localhost",
                               "https_proxy": "http://localhost:3128"})
        for nome in ("SEGREDO_TOKEN", "PYTHONPATH", "PYTHONSTARTUP", "LD_PRELOAD", "BASH_ENV", "FUNDACAO_PORTEIRO",
                     "SSH_AUTH_SOCK", "PYTHONHOME"):
            self.assertNotIn(nome, env)
        env = self.ex.ambiente_do_script({"HOME": "relativo", "TMPDIR": "x", "LANG": "pt;rm", "HTTP_PROXY": "a\nb"}, PROJETO)
        self.assertEqual((env["HOME"], env["TMPDIR"], env["LANG"], "HTTP_PROXY" in env),
                         ("/nonexistent", "/tmp", "C.UTF-8", False))

    def test_argumento_livre_nunca_vira_opcao_do_python(self):
        livres = ["-c", "import os; os.system('x')", "-m", "pip", "-X", "dev", "-I", "-", "--", "--version", "-W", "error"]
        self.assertEqual(self.executar(CHAVE, "buscar", "--", *livres)[0], 0)
        argv = self.rodar.chamadas[0]["argv"]
        self.assertEqual(argv[1:3], ["-I", "-B"])  # as opções do Python acabam no caminho absoluto do script
        self.assertTrue(os.path.isabs(argv[3]) and argv[3].endswith("buscar.py"))
        self.assertEqual(argv[4:], livres)

    def test_argumento_sem_o_separador_e_acima_do_teto_recusam(self):
        for cli in ((CHAVE, "buscar", "-c", "x"), (CHAVE, "buscar", "--", *["a"] * 65), (CHAVE, "buscar", "--", "a" * 4097)):
            with self.subTest(str(cli)[:40]):
                self.nada_rodou(*self.executar(*cli))

    def test_codigo_de_sinal_vira_128_mais_o_numero_e_falha_do_fim_do_registro_nao_muda_o_codigo(self):
        self.rodar.codigo = -9
        original = self.ex.registrar
        chamadas = []

        def registrar(proj, linha):
            chamadas.append(linha["fase"])
            if linha["fase"] == "fim":
                raise OSError("disco cheio")
            return original(proj, linha)
        with unittest.mock.patch.object(self.ex, "registrar", registrar):
            codigo, erro = self.executar(CHAVE, "buscar")
        self.assertEqual((codigo, chamadas), (137, ["inicio", "fim"]))
        self.assertIn("não foi registrado", erro)


class SoRodaPeloNomeDaFicha(Cenario):
    def test_n_sk_2_caminho_no_lugar_do_nome_ou_script_fora_da_ficha(self):
        ruins = [(CHAVE, SCRIPT_REL), (CHAVE, str(self.script)), (CHAVE, "../buscar"), (CHAVE, "-c"), (CHAVE, "buscar.py"),
                 (CHAVE, "outro"), (CHAVE, "BUSCAR"), ("busca", "buscar"), (f"{PLUGIN}:outra", "buscar"),
                 (f"{self.script}:busca", "buscar"), (f"../outro-projeto-busca:busca", "buscar"),
                 ("outro-projeto-busca:busca", "buscar"), ("-c:x", "buscar"), ("", "buscar")]
        for alvo, script in ruins:
            with self.subTest(alvo=alvo, script=script):
                self.nada_rodou(*self.executar(alvo, script))
        self.nada_rodou(*self.executar(CHAVE))  # sem o script
        self.nada_rodou(*self.executar())

    def test_n_sk_2_plugin_de_outro_projeto_e_ficha_que_nao_vale(self):
        self.ficha["projeto"] = "lab-a"
        self.gravar()
        self.nada_rodou(*self.executar(CHAVE, "buscar"), "projeto")
        self.ficha.update(projeto=PROJETO, valida=False)
        self.gravar()
        self.nada_rodou(*self.executar(CHAVE, "buscar"), "não vale")

    def test_o_lancador_com_opcoes_fora_da_forma_recusa(self):
        mau = [["--projeto", "Maiusculo"], ["--projeto", PROJETO, "--projeto", PROJETO], ["--projeto", PROJETO, "--area", "rel"],
               ["--projeto", PROJETO, "--outra", "x"], ["--projeto"], []]
        for opcoes in mau:
            with self.subTest(opcoes):
                self.nada_rodou(*self.executar(CHAVE, "buscar", opcoes=opcoes))
        with contextlib.redirect_stderr(io.StringIO()):
            codigo = self.ex.executar(["--projeto", PROJETO, CHAVE, "buscar"], self.ambiente, str(self.proj))  # sem o `--`
        self.assertEqual(codigo, 2)

    def test_modo_caixa_fica_fechado_com_a_mensagem(self):
        self.ficha = self.ficha_de("caixa")
        self.gravar()
        self.nada_rodou(*self.executar(CHAVE, "buscar"), "S4")

    def test_area_sem_arquivo_ou_ilegivel_recusa(self):
        (self.area / "hashes.json").write_text("{nao é json", encoding="utf-8")
        self.nada_rodou(*self.executar(CHAVE, "buscar"), "preparar-wsl.sh")
        (self.area / "hashes.json").unlink()
        self.nada_rodou(*self.executar(CHAVE, "buscar"))
        shutil.rmtree(self.area)
        self.nada_rodou(*self.executar(CHAVE, "buscar"))

    def test_hashes_de_outro_projeto_ou_outra_raiz_recusa(self):
        for mudanca in ({"projeto": "lab-a"}, {"raiz": "relativa"}, {"raiz": str(self.tmp / "nao-existe")}):
            with self.subTest(mudanca):
                self.hashes = {**self.hashes_de(), **mudanca}
                self.gravar()
                self.nada_rodou(*self.executar(CHAVE, "buscar"))


class SoRodaOQueFoiAssinado(Cenario):
    def test_n_hash_2_script_trocado_na_copia_root_o_executor_recusa_e_diz_qual(self):
        self.script.write_text(SCRIPT + "# um byte a mais\n", encoding="utf-8", newline="\n")
        self.nada_rodou(*self.executar(CHAVE, "buscar"), SCRIPT_REL)
        escrever(self.area / "plugins" / PLUGIN, SCRIPT_REL, SCRIPT)
        self.assertEqual(self.executar(CHAVE, "buscar")[0], 0)  # de volta ao assinado, roda

    def test_script_que_virou_ligacao_recusa_mesmo_com_o_mesmo_conteudo(self):
        alvo = self.tmp / "fora.py"
        alvo.write_text(SCRIPT, encoding="utf-8", newline="\n")
        self.script.unlink()
        try:
            self.script.symlink_to(alvo)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"link simbólico indisponível: {exc}")
        self.nada_rodou(*self.executar(CHAVE, "buscar"))

    def test_caminho_da_ficha_fora_da_forma_recusa(self):
        for caminho in ("../../x.py", "skills/outra/scripts/buscar.py", "skills/busca/scripts/buscar.sh",
                        "skills/busca/scripts/sub/buscar.py", "/etc/passwd"):
            with self.subTest(caminho):
                self.ficha["plugins"][0]["skills_com_scripts"][0]["scripts"][0]["caminho"] = caminho
                self.gravar()
                self.nada_rodou(*self.executar(CHAVE, "buscar"))

    def test_n_hash_4_arquivo_da_venv_mudado_a_mais_ou_a_menos_recusa(self):
        site = self.venv / "lib" / "python3.12" / "site-packages"
        estragos = {"arquivo mudado": lambda: escrever(site, "ensaio_um/__init__.py", "VALOR = 'mexido'\n"),
                    "arquivo a mais (.pth roda a cada partida)": lambda: escrever(site, "x.pth", "import os\n"),
                    "arquivo a menos": lambda: (site / "ensaio_um" / "__init__.py").unlink(),
                    "python da venv trocado": lambda: escrever(self.venv, "bin/python", "outro binario\n")}
        for nome, estraga in estragos.items():
            with self.subTest(nome):
                shutil.rmtree(self.venv)
                escrever(self.venv, "pyvenv.cfg", "home = /usr/bin\n")
                escrever(self.venv, "bin/python", "binario de ensaio\n")
                escrever(site, "ensaio_um/__init__.py", "VALOR = 'um'\n")
                estraga()
                self.nada_rodou(*self.executar(CHAVE, "buscar"), "mudou desde o preparo")

    def test_n_hash_4_venv_com_ligacao_que_sai_dela_ou_ausente_recusa(self):
        try:
            os.symlink("/usr/bin/python3", self.venv / "mau")
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"link simbólico indisponível: {exc}")
        self.nada_rodou(*self.executar(CHAVE, "buscar"), "venv")
        os.unlink(self.venv / "mau")
        shutil.rmtree(self.venv)
        self.nada_rodou(*self.executar(CHAVE, "buscar"), "venv")

    def test_n_hash_4_interpretador_diferente_recusa(self):
        self.python.write_bytes(b"interpretador trocado\n")
        self.nada_rodou(*self.executar(CHAVE, "buscar"), "interpretador")
        self.python.write_bytes(b"interpretador de ensaio\n")
        outro = self.python.with_name("python3.13")
        outro.write_bytes(b"interpretador de ensaio\n")  # o mesmo conteúdo, mas o python3 do sistema aponta para outro arquivo
        with unittest.mock.patch.object(self.ps, "PYTHON", str(outro)):
            self.nada_rodou(*self.executar(CHAVE, "buscar"), "agora aponta")

    def test_venv_registrada_que_nao_e_a_da_ficha_recusa(self):
        casos = {"lock diferente": lambda: self.hashes["skills"][CHAVE]["venv"].update(lock_sha256="b2" * 32),
                 "pasta fora da esperada": lambda: self.hashes["skills"][CHAVE]["venv"].update(
                     caminho=(self.tmp / "outra" / "venv").as_posix()),
                 "sem venv, a ficha pede pacotes": lambda: self.hashes["skills"][CHAVE].update(venv=None),
                 "skill sem registro": lambda: self.hashes["skills"].pop(CHAVE),
                 "interpretador fora da forma": lambda: self.hashes["skills"][CHAVE].update(interpretador={"caminho": "x"})}
        for nome, muda in casos.items():
            with self.subTest(nome):
                self.hashes = self.hashes_de()
                muda()
                self.gravar()
                self.nada_rodou(*self.executar(CHAVE, "buscar"))
        self.ficha, self.hashes = self.ficha_de("sessao", com_pacotes=False), self.hashes_de()
        self.gravar()
        self.nada_rodou(*self.executar(CHAVE, "buscar"), "não tem pacotes")  # a ficha não pede pacotes e o hashes registra venv


class TravaDoProjeto(Cenario):
    """N-SK-4: a sessão de outro projeto alcança este executor; a pasta atual e a variável o recusam (trava lógica)."""

    def test_pasta_atual_em_outro_projeto_ou_fora_recusa(self):
        outro = self.raiz / "projects" / "lab-a"
        for cwd in (outro, self.tmp, self.raiz, self.raiz / "projects", self.proj / ".." / "lab-a"):
            with self.subTest(cwd=str(cwd)):
                self.nada_rodou(*self.executar(CHAVE, "buscar", cwd=cwd), "este executor é do projeto")

    def test_pasta_dentro_do_projeto_vale_e_a_variavel_de_outro_projeto_nao(self):
        fundo = self.proj / "outputs" / "x"
        fundo.mkdir(parents=True)
        self.assertEqual(self.executar(CHAVE, "buscar", cwd=fundo)[0], 0)
        self.assertEqual(self.rodar.chamadas[-1]["cwd"], str(fundo))
        n = len(self.rodar.chamadas)
        for valor in ("lab-a", "", PROJETO + "x"):
            with self.subTest(variavel=valor):
                codigo, erro = self.executar(CHAVE, "buscar", ambiente={**self.ambiente, "FUNDACAO_PROJECT": valor})
                self.assertEqual(codigo, 2, erro)
                self.assertIn("FUNDACAO_PROJECT", erro)
        self.assertEqual(len(self.rodar.chamadas), n)

    def test_s3_variavel_ausente_de_outro_projeto_e_pasta_de_outro_projeto_recusam_sem_gravar_o_inicio(self):
        """`env -u FUNDACAO_PROJECT` + `cd` para este projeto não abre a trava: a variável é obrigatória (com a raiz em
        /mnt/<x> o isolamento é lógico). Cada caso recusa sem rodar e sem a linha de início no registro."""
        sem = {k: v for k, v in self.ambiente.items() if k != "FUNDACAO_PROJECT"}
        codigo, erro = self.executar(CHAVE, "buscar", ambiente=sem)
        self.nada_rodou(codigo, erro, "ausente")
        self.assertIn("FUNDACAO_PROJECT", erro)
        codigo, erro = self.executar(CHAVE, "buscar", ambiente={**sem, "FUNDACAO_PROJECT": "lab-a"})
        self.nada_rodou(codigo, erro, "em outro valor")
        outra = self.raiz / "projects" / "lab-a"
        self.nada_rodou(*self.executar(CHAVE, "buscar", cwd=outra), "este executor é do projeto")
        self.nada_rodou(*self.executar(CHAVE, "buscar", cwd=outra, ambiente={**sem, "FUNDACAO_PROJECT": "lab-a"}))
        self.assertEqual(self.executar(CHAVE, "buscar")[0], 0)  # a sessão certa roda

    def test_pasta_do_projeto_que_e_ligacao_recusa(self):
        mover = self.raiz / "projects" / "real"
        self.proj.rename(mover)
        try:
            self.proj.symlink_to(mover, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"link simbólico indisponível: {exc}")
        self.assertEqual(self.executar(CHAVE, "buscar", cwd=mover)[0], 2)
        self.assertEqual(self.rodar.chamadas, [])


class RegistroObrigatorio(Cenario):
    def test_sem_o_registro_gravado_o_script_nao_roda(self):
        saidas = self.proj / "outputs"
        saidas.mkdir()
        alvo = self.tmp / "outro-lugar"
        alvo.mkdir()
        try:
            (saidas / "skills").symlink_to(alvo, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"link simbólico indisponível: {exc}")
        codigo, erro = self.executar(CHAVE, "buscar")
        self.assertEqual((codigo, self.rodar.chamadas), (2, []))
        self.assertIn("registro", erro)
        self.assertEqual(list(alvo.iterdir()), [])  # nada gravado através da ligação

    def test_registro_que_e_pasta_ou_so_cresce(self):
        pasta = self.proj / "outputs" / "skills"
        (pasta / "registro.jsonl").mkdir(parents=True)
        self.assertEqual(self.executar(CHAVE, "buscar")[0], 2)
        shutil.rmtree(pasta / "registro.jsonl")
        self.executar(CHAVE, "buscar")
        self.executar(CHAVE, "buscar", "--", "x")
        self.assertEqual([l["fase"] for l in self.registro()], ["inicio", "fim", "inicio", "fim"])
        self.assertEqual(self.registro()[2]["argv"], ["x"])

    def test_argv_do_registro_e_truncado(self):
        self.executar(CHAVE, "buscar", "--", "z" * 500, *[str(i) for i in range(30)])
        linha = self.registro()[0]
        self.assertEqual((len(linha["argv"]), linha["argc"], len(linha["argv"][0])), (16, 31, 123))


class LancadorDoExecutor(unittest.TestCase):
    """O modelo do lançador (preparo_host.executor_skill): valores fixados entre aspas simples, tudo conferido."""

    def setUp(self):
        self.m = carregar_preparo()
        self.valores = {"PROJETO": PROJETO, "AREA": f"/etc/fundacao-ia/projetos/{PROJETO}",
                        "SKILL": "/etc/fundacao-ia/skill/1.7.11-abc", "SKILLS_BASE": "/usr/local/lib/fundacao-ia/skills",
                        "EXECUTOR_SHA256": "1" * 64, "PREPARO_SKILLS_SHA256": "2" * 64, "COPIA_SEGURA_SHA256": "3" * 64}

    def test_o_texto_fixa_os_valores_e_chama_o_executor_sem_privilegio(self):
        texto = self.m.executor_skill(self.valores)
        self.assertTrue(texto.startswith("#!/usr/bin/env bash\n"))
        self.assertNotIn("\r", texto)
        for trecho in (f"PROJETO='{PROJETO}'", "SKILLS_BASE='/usr/local/lib/fundacao-ia/skills'",
                       "confere 'assets/host/wsl/executor_skill.py' '" + "1" * 64 + "'",
                       "confere 'assets/host/preparo_skills.py' '" + "2" * 64 + "'",
                       "confere 'scripts/copia_segura.py' '" + "3" * 64 + "'",
                       'exec /usr/bin/python3 -I -B "$SKILL/$EXECUTOR" --projeto "$PROJETO" --area "$AREA" '
                       '--skills-base "$SKILLS_BASE" -- "$@"'):
            self.assertIn(trecho, texto)
        self.assertNotIn("sudo -", texto)
        self.assertNotIn("{{", texto)

    def test_sintaxe_do_bash(self):
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("sem bash neste ambiente")
        r = subprocess.run([bash, "-n"], input=self.m.executor_skill(self.valores).encode("utf-8"), capture_output=True,
                           timeout=60)  # bytes: no Windows o modo texto trocaria a quebra de linha por CRLF
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_aspas_no_caminho_nao_viram_comando_e_valor_fora_da_forma_recusa(self):
        texto = self.m.executor_skill({**self.valores, "SKILL": "/etc/it's here/$(id)"})
        self.assertIn("SKILL='/etc/it'\\''s here/$(id)'", texto)
        ruins = [{"SKILL": "relativo"}, {"AREA": ""}, {"EXECUTOR_SHA256": "xyz"}, {"PROJETO": "Maiusculo"},
                 {"SKILLS_BASE": "/x\ny"}, {"COPIA_SEGURA_SHA256": "A" * 64}]
        for mudanca in ruins:
            with self.subTest(mudanca):
                with self.assertRaises(self.m.EntradaInvalida):
                    self.m.executor_skill({**self.valores, **mudanca})
        with self.assertRaises(self.m.EntradaInvalida):
            self.m.executor_skill({k: v for k, v in self.valores.items() if k != "PROJETO"})
        with self.assertRaises(self.m.EntradaInvalida):  # marcador fora de aspas simples no modelo
            self.m.executor_skill(self.valores, "#!/usr/bin/env bash\necho {{PROJETO}}\n")


class ReconferenciaDoPreparo(unittest.TestCase):
    """O `conferir-abertura` chama `preparo_skills.problemas_da_abertura` (as mesmas funções do executor): aqui a função, com
    o preparo carregado como ele carrega (a classe de erro dele)."""

    def setUp(self):
        self.m = carregar_preparo()
        self.ps = self.m.preparo_skills()
        self.tmp = Path(tempfile.mkdtemp(prefix="executor-s3-r-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.python = self.tmp / "bin-falso" / "python3.12"
        escrever(self.python.parent, "python3.12", "interpretador de ensaio\n")
        patch = unittest.mock.patch.object(self.ps, "PYTHON", str(self.python))
        patch.start()
        self.addCleanup(patch.stop)
        self.venv = self.tmp / "venv"
        escrever(self.venv, "pyvenv.cfg", "home = /usr/bin\n")
        escrever(self.venv, "lib/x/__init__.py", "X = 1\n")
        inter = {"caminho": os.path.realpath(self.python), "sha256": hashlib.sha256(self.python.read_bytes()).hexdigest()}
        venv = {"caminho": self.venv.as_posix(), "sha256": self.ps.sha256_da_venv(self.ps.arvore_da_venv(self.venv))}
        self.hashes = {"skills": {CHAVE: {"interpretador": inter, "venv": venv}}}

    def test_igual_nao_acusa_e_sem_a_chave_nada_e_conferido(self):
        self.assertEqual(self.ps.problemas_da_abertura(self.hashes), [])
        self.assertEqual(self.ps.problemas_da_abertura({}), [])
        self.assertEqual(self.ps.problemas_da_abertura({"skills": {CHAVE: {"interpretador": self.hashes["skills"][CHAVE][
            "interpretador"], "venv": None}}}), [])

    def test_n_hash_4_venv_mexida_interpretador_trocado_e_registro_fora_da_forma_acusam(self):
        escrever(self.venv, "lib/x/__init__.py", "X = 2\n")
        (problema,) = self.ps.problemas_da_abertura(self.hashes)
        self.assertIn(f"skill {CHAVE}: a venv", problema)
        self.assertIn("mudou desde o preparo", problema)
        escrever(self.venv, "lib/x/__init__.py", "X = 1\n")
        self.python.write_bytes(b"outro\n")
        (problema,) = self.ps.problemas_da_abertura(self.hashes)
        self.assertIn("o interpretador", problema)
        for ruim in ("texto", ["lista"]):
            (problema,) = self.ps.problemas_da_abertura({"skills": ruim})
            self.assertIn("fora da forma", problema)
        (problema,) = self.ps.problemas_da_abertura({"skills": {CHAVE: {"interpretador": {"caminho": "relativo"}}}})
        self.assertIn("interpretador na forma esperada", problema)


# ------------------------------------------------------------------ os de Linux (L)
def _ambiente_de_verdade(casa: Path) -> dict:
    return {"PATH": "/usr/bin:/bin", "HOME": str(casa), "TMPDIR": str(casa), "LANG": "C.UTF-8",
            "FUNDACAO_PROJECT": PROJETO, **{
        k: v for k, v in HOME_FALSO.items() if k not in ("LANG", "LD_PRELOAD")}}


SONDA = """import json, os, sys
print(json.dumps({"argv": sys.argv[1:], "isolado": sys.flags.isolated, "sem_bytecode": sys.flags.dont_write_bytecode,
                  "env": sorted(os.environ), "cwd": os.getcwd(), "nome": sys.argv[0].rsplit("/", 1)[-1]}))
sys.exit(int(sys.argv[1]) if sys.argv[1:2] and sys.argv[1].isdigit() else 0)
"""


@unittest.skipUnless(LINUX and os.path.exists("/usr/bin/python3"), "o Python do sistema do Ubuntu. NÃO RODADO no Windows")
class ExecutorComOPythonDoSistema(unittest.TestCase):
    """L: o executor de verdade (processo à parte, `python3 -I -B`), sem venv: o script sonda roda isolado."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="executor-s3-l-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.raiz = self.tmp / "Raiz de Ensaio"
        self.proj = self.raiz / "projects" / PROJETO
        self.proj.mkdir(parents=True)
        (self.raiz / "projects" / "lab-a").mkdir()
        self.area, self.casa = self.tmp / "area" / "projetos" / PROJETO, self.tmp / "casa"
        self.casa.mkdir()
        escrever(self.area / "plugins" / PLUGIN, SCRIPT_REL, SONDA)
        real = os.path.realpath("/usr/bin/python3")
        ficha = {"projeto": PROJETO, "valida": True, "plugins": [{"nome": PLUGIN, "skills_com_scripts": [{
            "skill": "busca", "skill_md_sha256": "b" * 64, "scripts": [{
                "nome": "buscar", "caminho": SCRIPT_REL, "sha256": hashlib.sha256(SONDA.encode()).hexdigest(),
                "modo": "sessao"}]}]}]}
        self.hashes = {"projeto": PROJETO, "raiz": self.raiz.as_posix(), "skills": {CHAVE: {"interpretador": {
            "caminho": real, "sha256": hashlib.sha256(Path(real).read_bytes()).hexdigest(), "versao": "3.12"},
            "venv": None}}}
        (self.area / "aberturas.json").write_text(json.dumps(ficha), encoding="utf-8", newline="\n")
        self.gravar_hashes()

    def gravar_hashes(self) -> None:
        (self.area / "hashes.json").write_text(json.dumps(self.hashes), encoding="utf-8", newline="\n")

    def executar(self, *cli, cwd=None, env=None) -> subprocess.CompletedProcess:
        return subprocess.run(["/usr/bin/python3", "-I", "-B", str(EXECUTOR), "--projeto", PROJETO, "--area", str(self.area),
                               "--skills-base", str(self.tmp / "skills"), "--", *cli], cwd=str(cwd or self.proj),
                              env=env if env is not None else _ambiente_de_verdade(self.casa), stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=120)

    def test_roda_isolado_com_ambiente_minimo_e_devolve_o_codigo(self):
        r = self.executar(CHAVE, "buscar", "--", "3", "-c", "import os; os.system('x')", "-m", "pip", "--", "-I")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        saida = json.loads(r.stdout)
        self.assertEqual(saida["argv"], ["3", "-c", "import os; os.system('x')", "-m", "pip", "--", "-I"])
        self.assertEqual((saida["isolado"], saida["sem_bytecode"], saida["nome"]), (1, 1, "buscar.py"))
        self.assertEqual(Path(saida["cwd"]).resolve(), self.proj)
        permitido = {"PATH", "FUNDACAO_PROJECT", "LANG", "HOME", "TMPDIR", "HTTPS_PROXY", "NO_PROXY", "https_proxy", "LC_CTYPE"}
        self.assertLessEqual(set(saida["env"]), permitido)
        self.assertTrue({"PATH", "FUNDACAO_PROJECT", "HOME"} <= set(saida["env"]))
        fim = [json.loads(l) for l in (self.proj / "outputs" / "skills" / "registro.jsonl").read_text("utf-8").splitlines()]
        self.assertEqual([(l["fase"], l.get("codigo")) for l in fim], [("inicio", None), ("fim", 3)])

    def test_n_hash_2_script_trocado_nao_roda_e_nao_imprime_nada(self):
        escrever(self.area / "plugins" / PLUGIN, SCRIPT_REL, SONDA + "print('trocado')\n")
        r = self.executar(CHAVE, "buscar")
        self.assertEqual((r.returncode, r.stdout), (2, ""), r.stderr)
        self.assertIn(SCRIPT_REL, r.stderr)

    def test_n_hash_4_interpretador_com_hash_diferente_nao_roda(self):
        self.hashes["skills"][CHAVE]["interpretador"]["sha256"] = "0" * 64
        self.gravar_hashes()
        r = self.executar(CHAVE, "buscar")
        self.assertEqual((r.returncode, r.stdout), (2, ""), r.stderr)
        self.assertIn("interpretador", r.stderr)

    def test_n_sk_2_e_n_sk_4_nome_de_opcao_caminho_e_pasta_de_outro_projeto(self):
        for cli in (("-c", "x"), (CHAVE, "-c"), (CHAVE, str(self.area / "plugins" / PLUGIN / SCRIPT_REL)), (CHAVE, "outro")):
            with self.subTest(cli):
                r = self.executar(*cli)
                self.assertEqual((r.returncode, r.stdout), (2, ""), r.stderr)
        r = self.executar(CHAVE, "buscar", cwd=self.raiz / "projects" / "lab-a")
        self.assertEqual((r.returncode, r.stdout), (2, ""), r.stderr)
        r = self.executar(CHAVE, "buscar", env={**_ambiente_de_verdade(self.casa), "FUNDACAO_PROJECT": "lab-a"})
        self.assertEqual((r.returncode, r.stdout), (2, ""), r.stderr)
        sem = {k: v for k, v in _ambiente_de_verdade(self.casa).items() if k != "FUNDACAO_PROJECT"}
        r = self.executar(CHAVE, "buscar", env=sem)  # variável ausente
        self.assertEqual((r.returncode, r.stdout), (2, ""), r.stderr)
        self.assertIn("ausente", r.stderr)
        self.assertFalse((self.proj / "outputs").exists())


SCRIPT_COM_PACOTE = ("import sys, ensaio_um\nprint(ensaio_um.VALOR, sys.prefix != sys.base_prefix, *sys.argv[1:])\n")


@unittest.skipUnless(LINUX and os.path.exists("/usr/bin/python3"), "o pip real só roda no Ubuntu. NÃO RODADO no Windows")
class LancadorInstaladoComVenvDeVerdade(unittest.TestCase):
    """L: instalar-projeto com o pip e a venv de verdade (rodas de teste geradas aqui, sem rede) e o `fundacao-skill-<p>`
    gerado, rodado como o usuário da sessão."""

    def setUp(self):
        pronto = subprocess.run(["/usr/bin/python3", "-I", "-c", "import ensurepip, sys; sys.exit(0 if sys.version_info[:2] "
                                 "== (3, 12) else 3)"], capture_output=True, stdin=subprocess.DEVNULL, timeout=60)
        if pronto.returncode != 0:
            self.skipTest("precisa do Python 3.12 do sistema com python3-venv (a lista medida do kit)")
        self.caso = _caso_de_instalacao(self)
        c = self.caso
        rodas = [gerar_roda(c.proj / RODAS_REL, "ensaio-um"), gerar_roda(c.proj / RODAS_REL, "ensaio-dois", codigo="DOIS = 2\n")]
        c.aprovar_canario()
        gravar_ficha_na_caixa(c.raiz, PROJETO, ficha_de_ensaio(PROJETO, 1, plugins=[
            montar_plugin(c.proj, c.m, rodas, script=SCRIPT_COM_PACOTE)]))
        r = _instalar_cli(c)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.relatorio = json.loads(r.stdout)
        self.lancador = c.base / "bin" / f"fundacao-skill-{PROJETO}"
        self.venv = Path(json.loads((c.area / "hashes.json").read_text(encoding="utf-8"))["skills"][CHAVE]["venv"]["caminho"])
        self.copia = next((c.base / "area" / "skill").iterdir())

    def rodar(self, *cli, cwd=None, env=None) -> subprocess.CompletedProcess:
        c = self.caso
        return subprocess.run([str(self.lancador), *cli], cwd=str(cwd or c.proj), stdin=subprocess.DEVNULL,
                              env=env or {"PATH": "/usr/bin:/bin", "HOME": str(c.base / "home"), "TMPDIR": str(c.base / "tmp"),
                                  "FUNDACAO_PROJECT": PROJETO},
                              capture_output=True, text=True, timeout=120)

    def test_o_lancador_roda_o_script_da_ficha_na_venv_e_registra(self):
        c = self.caso
        self.assertEqual(self.relatorio["executor"], self.lancador.as_posix())
        self.assertEqual(oct(self.lancador.stat().st_mode & 0o777), "0o755")
        r = self.rodar(CHAVE, "buscar", "--", "a", "-c")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "um True a -c"), r.stdout + r.stderr)
        linhas = (c.proj / "outputs" / "skills" / "registro.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(l)["fase"] for l in linhas], ["inicio", "fim"])
        self.assertEqual(c.m.conferir_abertura(c.raiz, PROJETO, c.area)["problemas"], [])

    def test_n_hash_4_arquivo_da_venv_mudado_o_lancador_recusa_e_a_abertura_tambem(self):
        c = self.caso
        arquivo = self.venv / "lib" / "python3.12" / "site-packages" / "ensaio_um" / "__init__.py"
        original = arquivo.read_bytes()
        os.chmod(arquivo, 0o644)
        arquivo.write_bytes(b"VALOR = 'mexido'\n")
        r = self.rodar(CHAVE, "buscar")
        self.assertEqual((r.returncode, r.stdout), (2, ""), r.stderr)
        self.assertIn("mudou desde o preparo", r.stderr)
        problemas = c.m.conferir_abertura(c.raiz, PROJETO, c.area)["problemas"]
        self.assertTrue([p for p in problemas if "a venv" in p and "mudou desde o preparo" in p], problemas)
        arquivo.write_bytes(original)
        self.assertEqual(self.rodar(CHAVE, "buscar").returncode, 0)

    def test_executor_trocado_na_copia_root_o_lancador_recusa_pelo_sha256(self):
        arquivo = self.copia / "assets" / "host" / "wsl" / "executor_skill.py"
        original = arquivo.read_bytes()
        os.chmod(arquivo, 0o644)
        arquivo.write_bytes(original + b"\n# mudou\n")
        r = self.rodar(CHAVE, "buscar")
        self.assertEqual((r.returncode, r.stdout), (2, ""), r.stderr)
        self.assertIn("mudou desde o preparo", r.stderr)
        arquivo.write_bytes(original)
        self.assertEqual(self.rodar(CHAVE, "buscar").returncode, 0)

    def test_n_sk_4_sessao_de_outro_projeto_com_a_pasta_ou_a_variavel_dela_e_recusada(self):
        c = self.caso
        r = self.rodar(CHAVE, "buscar", cwd=c.raiz / "projects" / "lab-a")
        self.assertEqual((r.returncode, r.stdout), (2, ""), r.stderr)
        r = self.rodar(CHAVE, "buscar", env={"PATH": "/usr/bin:/bin", "HOME": str(c.base / "home"), "FUNDACAO_PROJECT": "lab-a"})
        self.assertEqual((r.returncode, r.stdout), (2, ""), r.stderr)
        r = self.rodar(CHAVE, "buscar", env={"PATH": "/usr/bin:/bin", "HOME": str(c.base / "home")})  # `env -u`
        self.assertEqual((r.returncode, r.stdout), (2, ""), r.stderr)
        self.assertIn("ausente", r.stderr)


@unittest.skipUnless(LINUX, "a área do titular é do Ubuntu (WSL2): instalar-projeto só roda no Linux. NÃO RODADO no Windows")
class InstalarGravaOExecutorPipSimulado(unittest.TestCase):
    """U no Linux, a instalação inteira em ensaio e com o pip simulado: o lançador do executor, o hashes.json, o
    conferir-abertura (venv, interpretador e lançador) e o executor que sai quando a ficha não tem mais scripts."""

    def setUp(self):
        self.caso = _caso_de_instalacao(self)
        c = self.caso
        self.ps = c.m.preparo_skills()
        falso = c.base / "bin-falso" / "python3.12"
        falso.parent.mkdir()
        falso.write_bytes(b"interpretador de ensaio\n")
        self.falso, self.pip = falso, PipFalso()
        for alvo, valor in (("PYTHON", str(falso)), ("rodar", self.pip)):
            patch = unittest.mock.patch.object(self.ps, alvo, valor)
            patch.start()
            self.addCleanup(patch.stop)
        self.rodas = [gerar_roda(c.proj / RODAS_REL, "ensaio-um"), gerar_roda(c.proj / RODAS_REL, "ensaio-dois")]
        c.aprovar_canario()
        (c.base / "tmp").mkdir(exist_ok=True)
        self.lancador = c.base / "bin" / f"fundacao-skill-{PROJETO}"

    def ficha(self, item=None, versao: int = 1) -> None:
        secoes = {"plugins": [item]} if item else {}
        gravar_ficha_na_caixa(self.caso.raiz, PROJETO, ficha_de_ensaio(PROJETO, versao, **secoes))

    def instalar(self) -> dict:
        c = self.caso
        return c.m.instalar_projeto(
            simular=False, ensaio=True, raiz=c.raiz, projeto=PROJETO, titular="titular", claude=c.claude,
            claude_versao="2.1.302", claude_sha256=hashlib.sha256(c.claude.read_bytes()).hexdigest(), origem_hash="ensaio",
            perfil_windows="/mnt/c/Users/<usuario>", casa=str(c.base / "home"), usuario=usuario_atual(),
            area_raiz=str(c.base / "area"), bin_dir=str(c.base / "bin"), temp_base=str(c.base / "tmp"),
            sonda_interop_cmd=str(c.base / "sem-interop" / "cmd.exe"),
            sonda_interop_binfmt=str(c.base / "sem-interop" / "binfmt"), gerenciadas=str(c.base / "claude-code-gerenciado"),
            ferramenta_base=None, skills_base=str(c.base / "skills"), vigente=_vigente_de_ensaio())

    def problemas(self) -> list:
        c = self.caso
        return c.m.conferir_abertura(c.raiz, PROJETO, c.area)["problemas"]

    def test_grava_o_lancador_fixado_no_hashes_e_a_segunda_vez_nada_muda(self):
        c = self.caso
        self.ficha(montar_plugin(c.proj, c.m, self.rodas))
        rel = self.instalar()
        self.assertEqual(rel["executor"], self.lancador.as_posix())
        self.assertIn(("executor-skill", "criar"), [(a["item"], a["acao"]) for a in rel["acoes"]])
        self.assertEqual(oct(self.lancador.stat().st_mode & 0o777), "0o755")
        hashes = json.loads((c.area / "hashes.json").read_text(encoding="utf-8"))
        sha = hashlib.sha256(self.lancador.read_bytes()).hexdigest()
        self.assertEqual(hashes["executor"], {"caminho": self.lancador.as_posix(), "sha256": sha})
        self.assertEqual(hashes["arquivos"][self.lancador.as_posix()], sha)
        copia = Path(hashes["arvores"]["skill"]["caminho"])
        texto = self.lancador.read_text(encoding="utf-8")
        for chave, rel_arquivo in (("EXECUTOR", "assets/host/wsl/executor_skill.py"),
                                   ("PREPARO_SKILLS", "assets/host/preparo_skills.py"), ("COPIA_SEGURA", "scripts/copia_segura.py")):
            esperado = hashlib.sha256((copia / rel_arquivo).read_bytes()).hexdigest()
            self.assertIn(f"confere '{rel_arquivo}' '{esperado}'", texto)
        self.assertIn(f"SKILL='{copia.as_posix()}'", texto)
        self.assertIn(f"AREA='{c.area.as_posix()}'", texto)
        self.assertIn(f"SKILLS_BASE='{(c.base / 'skills').as_posix()}'", texto)
        self.assertEqual(self.problemas(), [])
        rel2 = self.instalar()
        self.assertIn(("executor-skill", "igual"), [(a["item"], a["acao"]) for a in rel2["acoes"]])

    def test_conferir_abertura_acha_venv_mudada_interpretador_trocado_e_lancador_mexido(self):
        c = self.caso
        self.ficha(montar_plugin(c.proj, c.m, self.rodas))
        self.instalar()
        venv = Path(json.loads((c.area / "hashes.json").read_text(encoding="utf-8"))["skills"][CHAVE]["venv"]["caminho"])
        arquivo = venv / "lib" / "python3.12" / "site-packages" / "ensaio_um" / "__init__.py"
        original = arquivo.read_bytes()
        arquivo.write_bytes(b"VALOR = 'mexido'\n")
        self.assertTrue([p for p in self.problemas() if "a venv" in p and "mudou desde o preparo" in p])  # N-HASH-4
        arquivo.write_bytes(original)
        (venv / "lib" / "python3.12" / "site-packages" / "x.pth").write_text("import os\n", encoding="utf-8")
        self.assertTrue([p for p in self.problemas() if "a venv" in p])
        (venv / "lib" / "python3.12" / "site-packages" / "x.pth").unlink()
        self.assertEqual(self.problemas(), [])
        self.falso.write_bytes(b"interpretador trocado\n")
        self.assertTrue([p for p in self.problemas() if "o interpretador" in p and "mudou desde o preparo" in p])
        self.falso.write_bytes(b"interpretador de ensaio\n")
        os.chmod(self.lancador, 0o644)
        self.lancador.write_text(self.lancador.read_text(encoding="utf-8") + "# mexido\n", encoding="utf-8", newline="\n")
        self.assertTrue([p for p in self.problemas() if self.lancador.as_posix() in p and "mudou desde o preparo" in p])

    def test_ficha_sem_scripts_tira_o_executor_e_a_chave_do_hashes(self):
        c = self.caso
        self.ficha(montar_plugin(c.proj, c.m, []))
        self.instalar()
        self.assertTrue(self.lancador.exists())
        self.ficha(None, versao=2)
        rel = self.instalar()
        self.assertIn(("executor-skill", "remover"), [(a["item"], a["acao"]) for a in rel["acoes"]])
        self.assertFalse(self.lancador.exists())
        hashes = json.loads((c.area / "hashes.json").read_text(encoding="utf-8"))
        self.assertNotIn("executor", hashes)
        self.assertNotIn("skills", hashes)
        self.assertEqual(self.problemas(), [])

    def test_sem_skill_com_scripts_o_conferir_abertura_nao_pede_nada(self):
        self.ficha(None)
        self.instalar()
        self.assertFalse(self.lancador.exists())
        self.assertEqual(self.problemas(), [])


if __name__ == "__main__":
    unittest.main()
