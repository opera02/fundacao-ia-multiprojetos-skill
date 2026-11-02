"""Integração do fluxo B na 1.7.10 (pacote INTEG-FLUXOB do lote 2), itens 2 e 3, no perfil de execução
(`scripts/perfil_execucao.py`, pelo ponto de entrada `scripts/execucao_isolada.py`).

Item 2 (contratos do lote 2, §3): as máscaras da caixa saem da regra única. Dentro do código preso (a raiz do código de
terceiros, com a venv), só os nomes fortes; fora dele, os fortes e as pastas de segredo; os fracos nunca. As listas da
regra estão congeladas e têm `*credentials*` e `*.pem` entre os fortes: por isso o `botocore/credentials.py` e o
`certifi/cacert.pem` de uma venv ficam escondidos (a opção mais segura; a folha do pacote esperava o contrário e a
contradição foi registrada nas pendências para o coordenador decidir). O plano e a folha dizem o que fica escondido.
Revisão do pacote: a pasta de segredo de nome não forte (`.aws`, `.kube`, `segredos`...) dentro do código preso recusa
(defeito 1: a máscara não a cobre e a caixa a leria), e o código preso só vale preso se a caixa não vê nele nada que o
manifesto não prende (defeito 2: o nome fraco da venv fora do manifesto, trocado depois do plano, rodava na caixa com
o plano dizendo PRESO). O B7 (`segredos.py conferir` e o manifesto refeito com `--incluir-fraco`) destrava.

Item 3: o `rodar` fica amarrado ao projeto do lançador (`FUNDACAO_PROJECT`, ou `FUNDACAO_PROJETO_TRAVADO`): o perfil
tem de ser desse projeto, o `--projeto` não troca de projeto, e sem a variável ele é obrigatório. Nada roda nestes
testes (o caminho do bubblewrap é injetado no plano); vale em qualquer sistema, salvo as ligações (POSIX). Dados
fictícios.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import ENV, SCRIPTS, criar_ligacao_dir, rodar_script

BWRAP = "/usr/bin/bwrap"
LANCADOR = ("FUNDACAO_PROJECT", "FUNDACAO_PROJETO_TRAVADO")
SEM_LANCADOR = {k: v for k, v in ENV.items() if k not in LANCADOR}
SITE = ".venv/lib/python3.12/site-packages"
TOKENIZER = f"{SITE}/tokenizers/tokenizer.py"  # nome fraco (*token*): fora do manifesto até o B7
PASTAS_SEM_NOME_FORTE = (".aws", ".kube", ".docker", ".ssh", ".gnupg", ".azure", ".envs", "segredos", ".segredos",
                         "_browser_profile", ".omniroute")


def carregar():
    spec = importlib.util.spec_from_file_location("_teste_integ_perfil", SCRIPTS / "execucao_isolada.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


EX = carregar()


def cli(*args, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", str(SCRIPTS / "execucao_isolada.py"), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=300)


def erro_de(r: subprocess.CompletedProcess) -> str:
    try:
        return json.loads(r.stderr.strip().splitlines()[-1])["erro"]
    except (ValueError, IndexError, KeyError):
        return r.stderr


class _Projeto(unittest.TestCase):
    def setUp(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="integ-perfil-")))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.raiz = self.base / "raiz"
        self.projeto = self.raiz / "projects" / "p"
        self.tools, self.alvos, self.codigo = self.projeto / "tools", self.projeto / "alvos", self.projeto / "codigo"
        arquivos = {
            self.raiz / "state" / "state.sqlite": "",
            self.tools / ".venv" / "pyvenv.cfg": "home = /usr/bin\n",
            self.tools / SITE / "botocore" / "credentials.py": "class Credentials: pass\n",
            self.tools / SITE / "certifi" / "cacert.pem": "certificados públicos fictícios\n",
            self.tools / TOKENIZER: "X = 1\n",
            self.tools / SITE / "moto" / "credentials" / "k.json": "{}\n",  # casa *credentials*: escondida
            self.tools / SITE / "pkg" / "__init__.py": "\n",
            self.tools / SITE / "pkg" / "__pycache__" / "m.cpython-312.pyc": "\0",
            self.tools / ".env": "CHAVE=valor-fictício\n", self.tools / "id_rsa": "fictício\n",
            self.alvos / "um.txt": "ALVO\n", self.alvos / ".aws" / "config": "[default]\n",
            self.codigo / "testes" / "a.txt": "A\n", self.codigo / ".env.example": "X=\n",
            self.codigo / "tokenizer.py": "X = 1\n", self.codigo / "password_reset.py": "X = 1\n",
            self.codigo / ".omniroute" / "x.db": "db\n", self.codigo / "Credentials" / "k.txt": "k\n"}
        for caminho, texto in arquivos.items():
            caminho.parent.mkdir(parents=True, exist_ok=True)
            caminho.write_text(texto, encoding="utf-8", newline="\n")
        for programa, pasta in (("run.sh", self.tools), ("prog.sh", self.codigo)):
            (pasta / programa).write_text("#!/bin/sh\necho ok\n", encoding="utf-8", newline="\n")
            os.chmod(pasta / programa, 0o755)
        self.saida = self.projeto / "outputs" / "execucao" / "saida"
        self.man = self.projeto / "outputs" / "execucao" / "manifesto-tools.json"

    def gravar(self, dados: dict, nome: str = "perfil.json") -> tuple[Path, str]:
        arquivo = self.projeto / "outputs" / "execucao" / nome
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        bruto = (json.dumps(dados, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        arquivo.write_bytes(bruto)
        return arquivo, hashlib.sha256(bruto).hexdigest()

    def comandos(self, **mudar) -> dict:
        dados = {"schema_version": EX.ESQUEMA_PERFIL, "perfil_id": "testes", "projeto": "p",
                 "tipo": EX.COMANDOS_DO_PROJETO, "motivo": "rodar os testes do projeto (fictício)",
                 "validade": "2099-12-31", "modelos": [{"nome": "roda", "argv": ["./prog.sh", "{caminhos}"]}],
                 "codigo": {"preso": False},
                 "montagens": {"trabalho": "codigo", "saida": "outputs/execucao/saida"}}
        dados.update(mudar)
        return dados

    def b7(self) -> tuple[str, str]:
        """O B7 do titular: confere o conteúdo do nome fraco e, com código 0, o leva para o manifesto."""
        r = rodar_script("segredos.py", "conferir", self.tools / TOKENIZER)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return "--incluir-fraco", TOKENIZER

    def terceiros(self, *extra) -> dict:
        r = rodar_script("manifesto.py", "criar", "--raiz", self.tools, "--saida", self.man,
                         "--incluir-pasta-ignorada", ".venv", *extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        sha = hashlib.sha256(self.man.read_bytes()).hexdigest()
        return self.comandos(tipo=EX.FERRAMENTAS_DE_TERCEIROS,
                             codigo={"preso": True, "raiz": "tools", "venv": "tools/.venv",
                                     "manifesto": "outputs/execucao/manifesto-tools.json", "manifesto_sha256": sha},
                             montagens={"somente_leitura": ["alvos"], "saida": "outputs/execucao/saida"},
                             modelos=[{"nome": "roda", "argv": ["./run.sh", "{caminho}", "--saida={saida}"]}])

    def argv(self) -> list:
        return ["./run.sh", self.alvos / "um.txt", "--saida=" + str(self.saida / "r")]

    def plano(self, dados: dict, argv: list) -> dict:
        arquivo, sha = self.gravar(dados)
        return EX.plano_do_perfil(EX.ler_perfil(arquivo, sha), [str(a) for a in argv], bwrap=BWRAP)

    def recusa_do_plano(self, dados: dict) -> str:
        with self.assertRaises(EX.Recusa) as ctx:
            self.plano(dados, self.argv())
        return str(ctx.exception)


class TestMascarasPelaRegraUnica(_Projeto):
    def test_no_codigo_preso_so_os_nomes_fortes_e_fora_dele_tambem_as_pastas(self):
        plano = self.plano(self.terceiros(*self.b7()), self.argv())
        mascaras = {(tipo, Path(c).relative_to(self.projeto).as_posix()) for tipo, c in plano["mascaras"]}
        site = f"tools/{SITE}"
        for esperada in (("arquivo", "tools/.env"), ("arquivo", "tools/id_rsa"),
                         # nomes fortes da lista congelada (`*credentials*`, `*.pem`): escondidos também na venv
                         ("arquivo", f"{site}/botocore/credentials.py"), ("arquivo", f"{site}/certifi/cacert.pem"),
                         ("pasta", f"{site}/moto/credentials"), ("pasta", "alvos/.aws")):
            self.assertIn(esperada, mascaras)
        caminhos = {c for _t, c in mascaras}
        for visivel in (f"tools/{TOKENIZER}", f"{site}/pkg/__pycache__", "alvos/um.txt"):
            self.assertNotIn(visivel, caminhos, "dentro do código preso o fraco levado e o __pycache__ ficam visíveis")
        self.assertIn("só os arquivos e pastas de nome forte", plano["mascaras_regra"])
        self.assertEqual(plano["codigo_executado"], EX.PRESO_PELO_PERFIL)
        EX.conferir_plano_do_perfil(plano, antes=True)  # a conferência de antes usa a mesma regra

    def test_fora_do_codigo_preso_fortes_e_pastas_pela_regra_normalizada(self):
        plano = self.plano(self.comandos(), ["./prog.sh", "testes/a.txt"])
        mascaras = {(tipo, Path(c).relative_to(self.codigo).as_posix()) for tipo, c in plano["mascaras"]}
        for esperada in (("pasta", ".omniroute"), ("pasta", "Credentials"), ("arquivo", ".env.example")):
            self.assertIn(esperada, mascaras)  # .omniroute entrou na regra única; caixa e exemplo como no host
        for fraco in ("tokenizer.py", "password_reset.py"):
            self.assertNotIn(fraco, {c for _t, c in mascaras})

    def test_a_folha_e_a_conferencia_dizem_o_que_fica_escondido_e_fora_do_manifesto(self):
        arquivo, _sha = self.gravar(self.terceiros(*self.b7()))
        res = EX.conferir_perfil(arquivo)
        escondidos = {Path(c).relative_to(self.projeto).as_posix() for c in res["mascaras"]}
        self.assertIn("tools/.env", escondidos)
        self.assertIn("alvos/.aws", escondidos)
        folha = res["para_a_folha"]
        self.assertIn("no código preso", folha)
        self.assertIn(f"hoje, {len(res['mascaras'])}:", folha)
        self.assertIn(str(self.tools / ".env"), folha)
        self.assertEqual(res["mascaras_regra"], EX.MASCARAS_REGRA)
        # Como no fluxo B (folha_do_plano.codigo): o que o manifesto não prende vai para a conferência e a folha.
        for item in (".env", f"{SITE}/pkg/__pycache__/", f"{SITE}/botocore/credentials.py"):
            self.assertIn(item, res["fora_do_manifesto"])
        self.assertNotIn(TOKENIZER, res["fora_do_manifesto"], "o fraco levado pelo B7 fica preso")
        self.assertIn("ATENÇÃO: o manifesto não prende", folha)
        self.assertIn(f"{SITE}/pkg/__pycache__/", folha)


class TestPastaDeSegredoNoCodigoPreso(_Projeto):
    """Defeito 1 da revisão: dentro do código preso só o nome forte fica escondido (§3); a pasta de segredo de outro
    nome ficaria à vista da caixa, que a devolveria pela saída. Recusa no plano, no conferir-perfil e antes de rodar."""

    def test_pasta_de_segredo_de_nome_nao_forte_recusa(self):
        regras = EX.PERFIL.REGRAS  # as onze da revisão são as pastas da regra única que não casam um nome forte
        self.assertEqual(set(PASTAS_SEM_NOME_FORTE), {p for p in regras.PASTAS_DE_SEGREDO
                                                      if regras.classificar(p, pastas=(), exemplos=()) != "forte"})
        dados = self.terceiros(*self.b7())
        arquivo, _sha = self.gravar(dados, "perfil-segredo.json")
        for nome in PASTAS_SEM_NOME_FORTE:
            with self.subTest(nome=nome):
                pasta = self.tools / SITE / "moto" / nome
                pasta.mkdir(parents=True)
                (pasta / "config").write_text("[default]\n", encoding="utf-8")
                try:
                    texto = self.recusa_do_plano(dados)
                    self.assertIn("pasta de segredo", texto)
                    self.assertIn("tire-a da raiz do código", texto)
                    with self.assertRaises(EX.Recusa):
                        EX.conferir_perfil(arquivo)
                finally:
                    shutil.rmtree(pasta)
        self.assertEqual(self.plano(dados, self.argv())["codigo_executado"], EX.PRESO_PELO_PERFIL)

    def test_arquivo_com_nome_de_pasta_de_segredo_tambem_recusa(self):
        dados = self.terceiros(*self.b7())
        (self.tools / SITE / "moto" / "segredos").write_text("fictício\n", encoding="utf-8")
        self.assertIn("pasta de segredo", self.recusa_do_plano(dados))

    def test_pasta_que_aparece_depois_do_plano_para_antes_de_rodar(self):
        plano = self.plano(self.terceiros(*self.b7()), self.argv())
        EX.conferir_plano_do_perfil(plano, antes=True)
        (self.tools / SITE / "moto" / ".kube").mkdir()
        (self.tools / SITE / "moto" / ".kube" / "config").write_text("x\n", encoding="utf-8")
        with self.assertRaises(EX.Recusa) as ctx:
            EX.conferir_plano_do_perfil(plano, antes=True)
        self.assertIn("pasta de segredo", str(ctx.exception))


class TestCodigoPresoSoComOQueOManifestoPrende(_Projeto):
    """Defeito 2 da revisão: o que o manifesto não prende e a caixa vê deixa o código NÃO PRESO; recusa com o passo
    pronto (o B7 para o nome fraco). Ficam fora sem recusa só o escondido, o __pycache__ e a ligação conferida."""

    def test_fraco_fora_do_manifesto_recusa_com_o_b7(self):
        dados = self.terceiros()
        texto = self.recusa_do_plano(dados)
        for trecho in ("o manifesto não prende", TOKENIZER, "segredos.py", "conferir", "--incluir-fraco",
                       "--incluir-pasta-ignorada '.venv'", "nada foi executado"):
            self.assertIn(trecho, texto)
        arquivo, _sha = self.gravar(dados, "perfil-sem-b7.json")
        with self.assertRaises(EX.Recusa):
            EX.conferir_perfil(arquivo)
        plano = self.plano(self.terceiros(*self.b7()), self.argv())  # depois do B7, preso
        self.assertEqual(plano["codigo_executado"], EX.PRESO_PELO_PERFIL)
        self.assertEqual(plano["codigo_nao_preso"], [])

    def test_fraco_da_venv_trocado_entre_o_plano_e_a_execucao_nao_roda(self):
        plano = self.plano(self.terceiros(*self.b7()), self.argv())
        EX.conferir_plano_do_perfil(plano, antes=True)
        (self.tools / TOKENIZER).write_text("import os  # trocado depois do plano\n", encoding="utf-8")
        with self.assertRaises(EX.Recusa) as ctx:
            EX.conferir_plano_do_perfil(plano, antes=True)
        self.assertIn("difere do manifesto", str(ctx.exception))

    def test_fraco_novo_na_venv_entre_o_plano_e_a_execucao_nao_roda(self):
        plano = self.plano(self.terceiros(*self.b7()), self.argv())
        (self.tools / SITE / "pygments").mkdir()
        (self.tools / SITE / "pygments" / "token.py").write_text("X = 1\n", encoding="utf-8")
        with self.assertRaises(EX.Recusa) as ctx:
            EX.conferir_plano_do_perfil(plano, antes=True)
        self.assertIn("novo fora do manifesto", str(ctx.exception))

    def test_rodar_com_o_fraco_trocado_depois_do_plano_recusa_antes_da_caixa(self):
        arquivo, sha = self.gravar(self.terceiros(*self.b7()))

        def trocar(_bwrap):  # a sessão troca o arquivo entre o plano e a conferência de antes
            (self.tools / TOKENIZER).write_text("import os\n", encoding="utf-8")
            return True

        with mock.patch.dict(os.environ, {}), mock.patch.object(EX.PERFIL, "bwrap_monta_por_descritor", trocar), \
                mock.patch.object(EX.PERFIL, "_rodar", side_effect=AssertionError("a caixa não pode rodar")):
            for nome in LANCADOR:
                os.environ.pop(nome, None)
            with self.assertRaises(EX.Recusa) as ctx:
                EX.rodar_perfil(arquivo, sha, [str(a) for a in self.argv()], projeto="p", bwrap=BWRAP)
        self.assertIn("antes de rodar", str(ctx.exception))
        self.assertFalse((self.projeto / "outputs" / "execucao" / "registro.jsonl").exists())

    def test_conferir_perfil_fora_do_linux_deixa_a_ligacao_para_o_linux(self):
        dados = self.terceiros(*self.b7())
        criar_ligacao_dir(self.tools / SITE / "pkg" / "dados", self.alvos)  # pasta do código que aponta para fora
        arquivo, _sha = self.gravar(dados)
        if sys.platform.startswith("linux"):
            with self.assertRaises(EX.Recusa) as ctx:
                EX.conferir_perfil(arquivo)
            self.assertIn("aponte-a para o sistema", str(ctx.exception))
        else:  # no Windows não há caixa, e a ligação criada no WSL nem se resolve: ela fica para o Linux, com aviso
            res = EX.conferir_perfil(arquivo)
            self.assertTrue(any("conferida no Linux" in a and "pkg/dados" in a for a in res["avisos"]), res["avisos"])

    def test_git_e_pasta_ignorada_no_codigo_preso_recusam(self):
        casos = {".git": (self.tools / ".git" / "HEAD", "o .git: tire-o da raiz do código"),
                 "node_modules": (self.tools / "node_modules" / "m" / "i.js", "--incluir-pasta-ignorada <nome>")}
        for nome, (caminho, trecho) in casos.items():
            with self.subTest(nome):
                caminho.parent.mkdir(parents=True)
                caminho.write_text("x\n", encoding="utf-8")
                try:
                    self.assertIn(trecho, self.recusa_do_plano(self.terceiros(*self.b7())))
                finally:
                    shutil.rmtree(self.tools / nome)


@unittest.skipIf(os.name == "nt", "ligação simbólica de arquivo: POSIX (no Windows exige privilégio)")
class TestLigacoesDoCodigoPreso(_Projeto):
    def setUp(self):
        super().setUp()
        (self.tools / ".venv" / "bin").mkdir()
        os.symlink("/usr/bin/env", self.tools / ".venv" / "bin" / "python")  # a da venv aponta para o sistema
        os.symlink("lib", self.tools / ".venv" / "lib64")  # e a pasta lib64 para a lib dela

    def test_ligacao_para_o_sistema_ou_para_o_codigo_preso_vale(self):
        plano = self.plano(self.terceiros(*self.b7()), self.argv())
        fora = plano["manifesto"]["fora_do_manifesto"]
        self.assertIn(".venv/bin/python (ligação)", fora)
        self.assertIn(".venv/lib64 (ligação)", fora)
        self.assertEqual(plano["codigo_executado"], EX.PRESO_PELO_PERFIL)
        EX.conferir_plano_do_perfil(plano, antes=True)
        os.unlink(self.tools / ".venv" / "bin" / "python")  # trocada depois do plano, para fora do que é preso
        os.symlink(self.alvos / "um.txt", self.tools / ".venv" / "bin" / "python")
        for antes in (True, False):
            with self.subTest(antes=antes), self.assertRaises(EX.Recusa) as ctx:
                EX.conferir_plano_do_perfil(plano, antes=antes)
            self.assertIn("ligação", str(ctx.exception))

    def test_ligacao_para_fora_ou_sem_alvo_recusa(self):
        dados = self.terceiros(*self.b7())
        casos = {"para os alvos": self.alvos / "um.txt", "sem alvo": "nao-existe.pth",
                 "para o que o manifesto não prende": "../pkg/__pycache__/m.cpython-312.pyc"}
        for nome, alvo in casos.items():
            with self.subTest(nome):
                ligacao = self.tools / SITE / "tokenizers" / "x.pth"
                os.symlink(alvo, ligacao)
                try:
                    texto = self.recusa_do_plano(dados)
                    self.assertIn("x.pth", texto)
                    self.assertIn("aponte-a para o sistema", texto)
                finally:
                    os.unlink(ligacao)


class TestRodarAmarradoAoLancador(_Projeto):
    def projeto_com(self, ambiente: dict, projeto):
        with mock.patch.dict(os.environ, ambiente, clear=False):
            for nome in LANCADOR:
                if nome not in ambiente:
                    os.environ.pop(nome, None)
            return EX.projeto_do_lancador(projeto)

    def test_projeto_do_lancador(self):
        self.assertEqual(self.projeto_com({"FUNDACAO_PROJECT": "p"}, None), "p")
        self.assertEqual(self.projeto_com({"FUNDACAO_PROJECT": "p"}, "p"), "p")
        self.assertEqual(self.projeto_com({"FUNDACAO_PROJETO_TRAVADO": "p"}, None), "p")
        self.assertEqual(self.projeto_com({}, "p"), "p")
        recusas = {"--projeto troca de projeto": ({"FUNDACAO_PROJECT": "p"}, "outro"),
                   "sem lançador e sem --projeto": ({}, None),
                   "dois projetos no lançador": ({"FUNDACAO_PROJECT": "p", "FUNDACAO_PROJETO_TRAVADO": "q"}, None)}
        for nome, (ambiente, projeto) in recusas.items():
            with self.subTest(nome), self.assertRaises(EX.Recusa):
                self.projeto_com(ambiente, projeto)

    def test_rodar_recusa_perfil_de_outro_projeto_e_sem_projeto(self):
        marca = self.base / "rodou.txt"
        (self.codigo / "prog.sh").write_text(f"#!/bin/sh\necho rodou > '{marca.as_posix()}'\n", encoding="utf-8",
                                             newline="\n")
        arquivo, sha = self.gravar(self.comandos())
        argv = ["rodar", "--perfil", arquivo, "--perfil-sha256", sha]
        casos = {"lançador de outro projeto": (argv, {"FUNDACAO_PROJECT": "outro"}, "perfil é do projeto p"),
                 "--projeto diferente do lançador": ([*argv, "--projeto", "outro"], {"FUNDACAO_PROJECT": "p"},
                                                     "não troca de projeto"),
                 "sem lançador e sem --projeto": (argv, {}, "--projeto")}
        for nome, (args, ambiente, trecho) in casos.items():
            with self.subTest(nome):
                r = cli(*args, "--", "./prog.sh", "testes/a.txt", env={**SEM_LANCADOR, **ambiente})
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn(trecho, erro_de(r))
        self.assertFalse(marca.exists(), "nada pode rodar")


if __name__ == "__main__":
    unittest.main()
