"""Execução pelo perfil aprovado pelo SHA-256 (1.7.10, desenho §8.4; escopo 0.10, respostas G3b e E1 do titular):
`scripts/execucao_isolada.py rodar --perfil <arq> --perfil-sha256 <h> -- <argv>` e `conferir-perfil`.

Em qualquer sistema: o perfil (`fundacao.perfil_execucao/1`) é conferido pelo SHA-256, pela validade, pelo esquema
estrito e pelo projeto onde fica; o argv casa com os modelos e os marcadores só aceitam caminhos das montagens; a raiz
e os outros projetos nunca são montados, só a pasta de saída é gravável e os caminhos de segredo ficam escondidos; no
tipo de terceiros, o manifesto (com a venv) prende o código, e o comando que o deixaria solto é recusado. A execução de
verdade só roda no Linux com um bubblewrap que abre (nos demais, pulada). Pastas, programas e dados fictícios.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from apoio import ENV, SCRIPTS

BWRAP = "/usr/bin/bwrap"  # caminho injetado nos testes que só montam o plano (nada roda)
# Sem o projeto do lançador herdado de quem roda os testes: o `rodar` usa FUNDACAO_PROJECT (integração da 1.7.10).
SEM_LANCADOR = {k: v for k, v in ENV.items() if k not in ("FUNDACAO_PROJECT", "FUNDACAO_PROJETO_TRAVADO")}


def carregar():
    spec = importlib.util.spec_from_file_location("_teste_execucao_perfil", SCRIPTS / "execucao_isolada.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


EX = carregar()


def cli(*args, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", str(SCRIPTS / "execucao_isolada.py"), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", env=env or ENV,
                          timeout=300)


def erro_de(r: subprocess.CompletedProcess) -> str:
    try:
        return json.loads(r.stderr.strip().splitlines()[-1])["erro"]
    except (ValueError, IndexError, KeyError):
        return r.stderr


class _Projeto(unittest.TestCase):
    def setUp(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="perfil-execucao-")))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.raiz = self.base / "raiz"
        self.projeto = self.raiz / "projects" / "p"
        self.outro = self.raiz / "projects" / "outro"
        self.codigo, self.alvos = self.projeto / "codigo", self.projeto / "alvos"
        self.saida = self.projeto / "outputs" / "execucao" / "saida"
        arquivos = {self.raiz / "state" / "state.sqlite": b"", self.raiz / "state" / "canario.txt": b"CANARIO-STATE\n",
                    self.outro / "x.txt": b"CANARIO-OUTRO\n", self.codigo / "testes" / "a.txt": b"CONTEUDO-A\n",
                    self.codigo / ".env": b"CHAVE=valor-ficticio-do-teste\n",
                    self.codigo / ".segredos" / "k.txt": b"CANARIO-PASTA-DE-SEGREDO\n",
                    self.codigo / "config" / "meu-secret.json": b"{}\n", self.alvos / "um.txt": b"ALVO-UM\n"}
        for caminho, conteudo in arquivos.items():
            caminho.parent.mkdir(parents=True, exist_ok=True)
            caminho.write_bytes(conteudo)
        self.programa("prog.sh", "echo ok\n")

    def programa(self, nome: str, corpo: str, pasta: Path | None = None) -> Path:
        caminho = (pasta or self.codigo) / nome
        caminho.write_text("#!/bin/sh\n" + corpo, encoding="utf-8", newline="\n")
        os.chmod(caminho, 0o755)
        return caminho

    def perfil(self, **mudar) -> dict:
        dados = {"schema_version": EX.ESQUEMA_PERFIL, "perfil_id": "testes", "projeto": "p",
                 "tipo": EX.COMANDOS_DO_PROJETO, "motivo": "rodar os testes do projeto (fictício)",
                 "validade": "2099-12-31",
                 "modelos": [{"nome": "roda", "argv": ["./prog.sh", "{caminhos}"]},
                             {"nome": "gera", "argv": ["./prog.sh", "--saida={saida}"]}],
                 "codigo": {"preso": False},
                 "montagens": {"trabalho": "codigo", "somente_leitura": ["alvos"], "saida": "outputs/execucao/saida"}}
        dados.update(mudar)
        return dados

    def gravar(self, dados: dict, nome: str = "perfil.json") -> tuple[Path, str]:
        arquivo = self.projeto / "outputs" / "execucao" / nome
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        bruto = (json.dumps(dados, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        arquivo.write_bytes(bruto)
        return arquivo, hashlib.sha256(bruto).hexdigest()

    def plano(self, dados: dict, argv: list) -> dict:
        arquivo, sha = self.gravar(dados)
        return EX.plano_do_perfil(EX.ler_perfil(arquivo, sha), [str(a) for a in argv], bwrap=BWRAP)


class TestPerfilEPlano(_Projeto):
    def test_plano_monta_so_o_projeto_esconde_segredo_e_so_a_saida_e_gravavel(self):
        plano = self.plano(self.perfil(), ["./prog.sh", "testes/a.txt", self.alvos / "um.txt"])
        self.assertEqual(plano["modelo"], "roda")
        self.assertEqual(plano["comando"][1:], [str(self.codigo / "testes" / "a.txt"), str(self.alvos / "um.txt")])
        self.assertTrue(plano["codigo_executado"].startswith("NÃO PRESO, por decisão do titular"))
        self.assertEqual(plano["rede"], EX.REDE_NEGADA)
        mascaras = {tuple(m) for m in plano["mascaras"]}
        for esperada in (("arquivo", str(self.codigo / ".env")), ("pasta", str(self.codigo / ".segredos")),
                         ("arquivo", str(self.codigo / "config" / "meu-secret.json"))):
            self.assertIn(esperada, mascaras)
        argv = EX.argv_bwrap_perfil(plano)
        opcoes = argv[:argv.index("--")]
        texto = " ".join(opcoes)
        for trecho in (f"--ro-bind {self.codigo} {self.codigo}", f"--ro-bind {self.alvos} {self.alvos}",
                       f"--bind {self.saida} {self.saida}", f"--ro-bind /dev/null {self.codigo / '.env'}",
                       f"--tmpfs {self.codigo / '.segredos'}", f"--chdir {self.codigo}"):
            self.assertIn(trecho, texto)
        for flag in ("--unshare-all", "--die-with-parent", "--new-session", "--clearenv"):
            self.assertIn(flag, opcoes)
        self.assertEqual(opcoes.count("--bind"), 1, "só a pasta de saída é gravável")
        self.assertLess(texto.index(f"--ro-bind {self.codigo} "), texto.index(f"--tmpfs {self.codigo / '.segredos'}"),
                        "a máscara vem depois da árvore")
        origens = {m[1] for m in plano["montagens"] if m[0] in ("ro-bind", "bind")}
        for proibida in (self.raiz, self.raiz / "state", self.raiz / "projects", self.outro, self.projeto, Path.home()):
            self.assertNotIn(str(proibida), origens)
        self.assertEqual(plano["ambiente"]["HOME"], "/tmp")
        self.assertFalse([k for k in plano["ambiente"] if k.startswith("FUNDACAO_")])
        self.assertTrue(self.saida.is_dir(), "a pasta de saída nasce no plano")

    def test_arvores_do_projeto_entram_por_descritor(self):
        plano = self.plano(self.perfil(), ["./prog.sh", "testes/a.txt"])
        descritores = {str(self.codigo): 7, str(self.alvos): 8, str(self.saida): 9}
        texto = " ".join(EX.argv_bwrap_perfil(plano, descritores))
        for trecho in (f"--ro-bind-fd 7 {self.codigo}", f"--ro-bind-fd 8 {self.alvos}", f"--bind-fd 9 {self.saida}",
                       "--ro-bind /usr /usr"):
            self.assertIn(trecho, texto)
        self.assertNotIn(f"--ro-bind {self.codigo} ", texto)
        self.assertNotIn(f"--bind {self.saida} ", texto)

    @unittest.skipUnless(sys.platform.startswith("linux"), "O_PATH e O_NOFOLLOW por componente: só no Linux")
    def test_ligacao_trocada_no_caminho_nao_abre(self):
        atalho = self.projeto / "atalho"
        atalho.symlink_to(self.outro, target_is_directory=True)
        for caminho in (atalho, atalho / "x.txt"):
            with self.subTest(str(caminho)), self.assertRaises(EX.Recusa):
                EX.abrir_sem_seguir(str(self.projeto), str(caminho))
        fd = EX.abrir_sem_seguir(str(self.projeto), str(self.alvos))
        os.close(fd)

    def test_marcador_de_saida_e_caminhos_fora_das_montagens(self):
        plano = self.plano(self.perfil(), ["./prog.sh", "--saida=" + str(self.saida / "r.json")])
        self.assertEqual((plano["modelo"], plano["comando"][1]), ("gera", "--saida=" + str(self.saida / "r.json")))
        recusados = {"sem caminho": ["./prog.sh"], "outro projeto": ["./prog.sh", self.outro / "x.txt"],
                     "subindo com ..": ["./prog.sh", "../../outro/x.txt"], "opção": ["./prog.sh", "-rf"],
                     "inexistente": ["./prog.sh", "testes/nada.txt"], "outro programa": ["/bin/sh", "testes/a.txt"],
                     "saída fora da saída": ["./prog.sh", "--saida=" + str(self.codigo / "r.json")],
                     "a raiz": ["./prog.sh", self.raiz / "state" / "canario.txt"]}
        for nome, argv in recusados.items():
            with self.subTest(nome), self.assertRaises(EX.Recusa):
                self.plano(self.perfil(), argv)

    def test_sha256_validade_e_projeto(self):
        arquivo, sha = self.gravar(self.perfil())
        with self.assertRaises(EX.Recusa) as ctx:
            EX.ler_perfil(arquivo, "0" * 64)
        self.assertIn("SHA-256 aprovado", str(ctx.exception))
        with self.assertRaises(EX.Recusa) as ctx:
            EX.ler_perfil(arquivo, sha, hoje=date(2100, 1, 1))
        self.assertIn("vencido", str(ctx.exception))
        with self.assertRaises(EX.Recusa):
            EX.ler_perfil(arquivo, sha, projeto="outro")
        arquivo, sha = self.gravar(self.perfil(projeto="outro"))
        with self.assertRaises(EX.Recusa):
            EX.ler_perfil(arquivo, sha)
        fora = self.base / "perfil.json"
        fora.write_bytes(arquivo.read_bytes())
        with self.assertRaises(EX.Recusa):
            EX.ler_perfil(fora, sha)

    def test_esquema_estrito(self):
        casos = {"campo desconhecido": self.perfil(extra=1),
                 "sem validade": {k: v for k, v in self.perfil().items() if k != "validade"},
                 "data fora do formato": self.perfil(validade="31/12/2099"),
                 "rede com domínio": self.perfil(rede={"dominios": ["exemplo.invalid"]}),
                 "variável de segredo": self.perfil(ambiente={"API_KEY": "x"}),
                 "variável da fundação": self.perfil(ambiente={"FUNDACAO_PROJECT": "p"}),
                 "variável reservada": self.perfil(ambiente={"PATH": "/tmp"}),
                 "tipo desconhecido": self.perfil(tipo="tudo"),
                 "código preso no primeiro tipo": self.perfil(codigo={"preso": True}),
                 "sem árvore de trabalho": self.perfil(montagens={"saida": "outputs/s"}),
                 "saída no .git": self.perfil(montagens={"trabalho": "codigo", "saida": "repo/.git/x"}),
                 "saída em decisoes": self.perfil(montagens={"trabalho": "codigo", "saida": "decisoes/x"}),
                 "trabalho fora do projeto": self.perfil(montagens={"trabalho": "../outro", "saida": "outputs/s"}),
                 "trabalho absoluto": self.perfil(montagens={"trabalho": str(self.codigo), "saida": "outputs/s"}),
                 "programa com marcador": self.perfil(modelos=[{"nome": "x", "argv": ["{caminho}"]}]),
                 "caminhos no meio": self.perfil(modelos=[{"nome": "x", "argv": ["./prog.sh", "{caminhos}", "-v"]}]),
                 "dois marcadores": self.perfil(modelos=[{"nome": "x", "argv": ["./prog.sh", "{caminho}{saida}"]}]),
                 "marcador desconhecido": self.perfil(modelos=[{"nome": "x", "argv": ["./prog.sh", "{texto}"]}]),
                 "limite acima do teto": self.perfil(limites={"tempo_s": 10 ** 6}),
                 "limite desconhecido": self.perfil(limites={"rede": 1})}
        for nome, dados in casos.items():
            with self.subTest(nome):
                arquivo, sha = self.gravar(dados)
                with self.assertRaises(EX.Recusa):
                    EX.ler_perfil(arquivo, sha)

    def test_saida_que_contem_arvore_e_pasta_de_trabalho_fora(self):
        dados = self.perfil(montagens={"trabalho": "codigo", "somente_leitura": ["outputs/execucao/saida/dados"],
                                       "saida": "outputs/execucao/saida"})
        (self.saida / "dados").mkdir(parents=True)
        with self.assertRaises(EX.Recusa) as ctx:
            self.plano(dados, ["./prog.sh", "testes/a.txt"])
        self.assertIn("contém uma árvore só leitura", str(ctx.exception))
        with self.assertRaises(EX.Recusa):
            self.plano(self.perfil(cwd="alvos/nao-existe"), ["./prog.sh", "testes/a.txt"])
        with self.assertRaises(EX.Recusa) as ctx:  # árvore que é ela mesma pasta de segredo não é montada
            EX.mascaras([str(self.codigo / ".segredos")])
        self.assertIn("nome de segredo", str(ctx.exception))

    def test_conferir_perfil_mostra_o_sha256_e_o_texto_da_folha(self):
        arquivo, sha = self.gravar(self.perfil())
        r = cli("conferir-perfil", "--perfil", arquivo, "--projeto", "p")
        self.assertEqual(r.returncode, 0, r.stderr)
        res = json.loads(r.stdout)
        self.assertEqual(res["sha256"], sha)
        # "1.7.11", não "ficha de aberturas": a folha prometia o perfil na ficha, cuja seção `execucao` é da 1.7.11
        # (revisão da terceira rodada da integração, defeito 3; TestFolhaERecusaSemPromessa, abaixo).
        for termo in ("NÃO PRESO", sha, "sem rede", "1.7.11", str(self.saida)):
            self.assertIn(termo, res["para_a_folha"])
        r = cli("conferir-perfil", "--perfil", arquivo, "--projeto", "outro")
        self.assertEqual(r.returncode, 2)

    def test_sem_bubblewrap_recusa_e_nada_roda(self):
        marca = self.base / "rodou.txt"
        self.programa("prog.sh", f"echo rodou > '{marca.as_posix()}'\n")
        arquivo, sha = self.gravar(self.perfil())
        vazio = self.base / "sem-programas"
        vazio.mkdir()
        r = cli("rodar", "--perfil", arquivo, "--perfil-sha256", sha, "--projeto", "p", "--", "./prog.sh",
                "testes/a.txt", env={**SEM_LANCADOR, "PATH": str(vazio)})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("bubblewrap", erro_de(r))
        self.assertFalse(marca.exists())
        r = cli("rodar", "--perfil", arquivo, "--perfil-sha256", "f" * 64, "--projeto", "p", "--", "./prog.sh",
                "testes/a.txt", env=SEM_LANCADOR)
        self.assertEqual(r.returncode, 2)
        self.assertIn("SHA-256", erro_de(r))


    def test_montagem_por_pasta_de_segredo_ou_reservada_recusa(self):
        casos = {
            "somente_leitura em secrets/": self.perfil(montagens={"trabalho": "codigo", "somente_leitura": ["secrets/x"],
                                                                  "saida": "outputs/execucao/saida"}),
            "trabalho em .segredos/": self.perfil(montagens={"trabalho": ".segredos/sub",
                                                            "saida": "outputs/execucao/saida"}),
            "saída em data": self.perfil(montagens={"trabalho": "codigo", "saida": "data/x"}),
            "saída em credentials": self.perfil(montagens={"trabalho": "codigo", "saida": "credentials/x"}),
            "saída contém o registro": self.perfil(montagens={"trabalho": "codigo", "saida": "outputs"}),
            "validade em formato básico": self.perfil(validade="20991231"),
        }
        for nome, dados in casos.items():
            with self.subTest(nome):
                arquivo, sha = self.gravar(dados)
                with self.assertRaises(EX.Recusa):
                    EX.ler_perfil(arquivo, sha)

    def test_marcador_que_aponta_para_segredo_recusa(self):
        for alvo in ("config/meu-secret.json", ".env", ".segredos/k.txt"):
            with self.subTest(alvo), self.assertRaises(EX.Recusa):
                self.plano(self.perfil(), ["./prog.sh", alvo])

    def test_destino_do_registro_so_em_outputs_jsonl_fora_da_saida(self):
        perfil = EX.ler_perfil(*self.gravar(self.perfil()))
        bom = self.projeto / "outputs" / "r.jsonl"
        self.assertEqual(EX._destino_do_registro(perfil, bom), bom)
        maus = {"fora de outputs": self.projeto / "x.jsonl", "não jsonl": self.projeto / "outputs" / "r.txt",
                "em decisoes": self.projeto / "outputs" / "decisoes" / "r.jsonl",
                "dentro da pasta gravável": self.saida / "r.jsonl", "fora do projeto": self.base / "r.jsonl"}
        for nome, destino in maus.items():
            with self.subTest(nome), self.assertRaises(EX.Recusa):
                EX._destino_do_registro(perfil, destino)

    def test_folha_mostra_ambiente_cwd_e_limites(self):
        perfil = EX.ler_perfil(*self.gravar(self.perfil(ambiente={"MINHA_VAR": "valor-x"})))
        texto = EX.folha_do_perfil(perfil)
        for termo in ("Pasta de trabalho:", "Ambiente: MINHA_VAR=valor-x", "processos", "arquivo até"):
            self.assertIn(termo, texto)
        self.assertIn("Ambiente: nenhum", EX.folha_do_perfil(EX.ler_perfil(*self.gravar(self.perfil(), "p2.json"))))

    def test_perfil_fora_de_uma_fundacao_recusa(self):
        outra = self.base / "outra" / "projects" / "p" / "outputs" / "execucao"
        outra.mkdir(parents=True)  # projects/<p>/ sem state/state.sqlite acima: não é uma fundação
        bruto = (json.dumps(self.perfil(), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        arquivo = outra / "perfil.json"
        arquivo.write_bytes(bruto)
        with self.assertRaises(EX.Recusa) as ctx:
            EX.ler_perfil(arquivo, hashlib.sha256(bruto).hexdigest())
        self.assertIn("fundação", str(ctx.exception))


class TestFerramentasDeTerceiros(_Projeto):
    def setUp(self):
        super().setUp()
        self.tools = self.projeto / "tools"
        (self.tools / ".venv" / "lib").mkdir(parents=True)
        (self.tools / ".venv" / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
        (self.tools / ".venv" / "lib" / "biblioteca.py").write_text("X = 1\n", encoding="utf-8")
        self.programa("run.sh", 'cat "$1"; echo saida > "${2#--saida=}"\n', self.tools)

    def manifesto(self, com_venv: bool = True) -> str:
        """O manifesto do código, com a venv incluída (fora das pastas ignoradas), como o `--incluir-pasta-ignorada`
        do manifesto da 1.7.10 faz."""
        m = EX.CODIGO.MANIFESTO
        politica = m.politica_padrao()
        if com_venv:
            politica["pastas_ignoradas"] = [p for p in politica["pastas_ignoradas"] if p != ".venv"]
        arquivo = self.projeto / "outputs" / "execucao" / "manifesto-tools.json"
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(json.dumps(m.build(self.tools, politica), ensure_ascii=False), encoding="utf-8")
        return hashlib.sha256(arquivo.read_bytes()).hexdigest()

    def terceiros(self, sha_manifesto: str, **mudar) -> dict:
        dados = self.perfil(tipo=EX.FERRAMENTAS_DE_TERCEIROS,
                            codigo={"preso": True, "raiz": "tools", "venv": "tools/.venv",
                                    "manifesto": "outputs/execucao/manifesto-tools.json",
                                    "manifesto_sha256": sha_manifesto},
                            montagens={"somente_leitura": ["alvos"], "saida": "outputs/execucao/saida"},
                            modelos=[{"nome": "roda", "argv": ["./run.sh", "{caminho}", "--saida={saida}"]}])
        dados.update(mudar)
        return dados

    def argv(self) -> list:
        return ["./run.sh", self.alvos / "um.txt", "--saida=" + str(self.saida / "r.txt")]

    def test_codigo_e_venv_presos_pelo_manifesto(self):
        plano = self.plano(self.terceiros(self.manifesto()), self.argv())
        self.assertEqual(plano["codigo_executado"], EX.PRESO_PELO_PERFIL)
        self.assertEqual(plano["copia"], str(self.tools))
        self.assertEqual(plano["ambiente"]["PYTHONPYCACHEPREFIX"], EX.PYCACHE_DA_CAIXA)
        self.assertEqual(plano["cwd"], str(self.tools))
        EX.conferir_plano_do_perfil(plano, antes=True)
        (self.tools / ".venv" / "lib" / "biblioteca.py").write_text("X = 2  # trocado\n", encoding="utf-8")
        with self.assertRaises(EX.Recusa) as ctx:
            EX.conferir_plano_do_perfil(plano, antes=True)
        self.assertIn("difere do manifesto", str(ctx.exception))

    def test_recusas_do_codigo_preso(self):
        sha = self.manifesto()
        casos = {"variável que carrega código": self.terceiros(sha, ambiente={"PYTHONPATH": "alvos"}),
                 "saída dentro do código": self.terceiros(sha, montagens={"somente_leitura": ["alvos"],
                                                                         "saida": "tools/saida"}),
                 "outro SHA-256 do manifesto": self.terceiros("a" * 64)}
        for nome, dados in casos.items():
            with self.subTest(nome), self.assertRaises(EX.Recusa):
                self.plano(dados, self.argv())
        with self.assertRaises(EX.Recusa) as ctx:
            self.plano(self.terceiros(self.manifesto(com_venv=False)), self.argv())
        self.assertIn("ignora a venv", str(ctx.exception))

    def test_modelo_com_caminho_no_lugar_do_script_e_recusado(self):
        dados = self.terceiros(self.manifesto(), modelos=[{"nome": "solto", "argv": ["/usr/bin/python3", "{caminho}"]}])
        arquivo, _sha = self.gravar(dados)
        with self.assertRaises(EX.Recusa) as ctx:
            EX.conferir_perfil(arquivo)
        self.assertIn("NÃO PRESO", str(ctx.exception))
        arquivo, _sha = self.gravar(self.terceiros(self.manifesto()))
        self.assertTrue(EX.conferir_perfil(arquivo)["valido"])


class TestCaixaDeVerdade(_Projeto):
    """Só onde o bubblewrap abre um sandbox (Linux/WSL com o preparo do host); nos demais, pulados."""

    def setUp(self):
        caminho, motivo = EX.sondar_bwrap()
        if not caminho:
            self.skipTest(f"bubblewrap não abre um sandbox aqui: {motivo}")
        super().setUp()

    def rodar(self, dados: dict, *argv) -> tuple[subprocess.CompletedProcess, dict]:
        arquivo, sha = self.gravar(dados)
        r = cli("rodar", "--perfil", arquivo, "--perfil-sha256", sha, "--projeto", "p", "--", *argv,
                env={**SEM_LANCADOR, "FUNDACAO_PROJECT": "p", "CANARIO_DO_LANCADOR": "canario-projeto"})
        return r, (json.loads(r.stdout) if r.stdout.strip() else {})

    def test_canarios_rede_segredo_raiz_outro_projeto_e_so_a_saida_gravavel(self):
        self.programa("prog.sh", (f'cat "$1"\n'
                                  'echo "ENV-LIDO:$(cat .env 2>/dev/null)"\n'
                                  'echo "SEGREDOS:$(ls .segredos 2>/dev/null | wc -l)"\n'
                                  f'cat "{self.raiz}/state/canario.txt" 2>/dev/null\n'
                                  f'cat "{self.outro}/x.txt" 2>/dev/null\n'
                                  '(echo x > novo.txt) 2>/dev/null && echo TRABALHO-GRAVAVEL\n'
                                  f'echo y > "{self.saida}/ok.txt" && echo SAIDA-GRAVAVEL\n'
                                  "echo INTERFACES $(tail -n +3 /proc/net/dev | cut -d: -f1 | tr -d ' ')\n"
                                  "env\n"))
        r, res = self.rodar(self.perfil(), "./prog.sh", "testes/a.txt")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        saida = res["stdout"]
        self.assertIn("CONTEUDO-A", saida)
        self.assertIn("ENV-LIDO:\n", saida)
        self.assertIn("SEGREDOS:0", saida)
        self.assertIn("SAIDA-GRAVAVEL", saida)
        self.assertIn("INTERFACES lo\n", saida, "rede além do lo próprio da caixa")
        for proibido in ("valor-ficticio-do-teste", "CANARIO-STATE", "CANARIO-OUTRO", "TRABALHO-GRAVAVEL",
                         "canario-projeto", "FUNDACAO_"):
            self.assertNotIn(proibido, saida)
        self.assertFalse((self.codigo / "novo.txt").exists())
        self.assertTrue((self.saida / "ok.txt").is_file())
        linhas = (self.projeto / "outputs" / "execucao" / "registro.jsonl").read_text(encoding="utf-8").splitlines()
        registro = json.loads(linhas[-1])
        self.assertEqual((registro["modelo"], registro["codigo"], registro["conferencia_depois"]), ("roda", 0, "ok"))
        self.assertEqual(registro["stdout_sha256"], hashlib.sha256(saida.encode("utf-8")).hexdigest())

    def test_prazo_estourado_e_codigo_diferente_de_zero(self):
        self.programa("prog.sh", "sleep 30\n")
        r, res = self.rodar(self.perfil(limites={"tempo_s": 2}), "./prog.sh", "testes/a.txt")
        self.assertEqual((r.returncode, res["codigo"]), (1, "timeout"))
        self.programa("prog.sh", "exit 7\n")
        r, res = self.rodar(self.perfil(), "./prog.sh", "testes/a.txt")
        self.assertEqual((r.returncode, res["codigo"]), (1, 7))

    def test_terceiros_roda_preso_e_codigo_trocado_nao_roda(self):
        tools = self.projeto / "tools"
        tools.mkdir()
        self.programa("run.sh", 'cat "$1"; echo gerado > "${2#--saida=}"\n', tools)
        m = EX.CODIGO.MANIFESTO
        manifesto = self.projeto / "outputs" / "execucao" / "manifesto-tools.json"
        manifesto.parent.mkdir(parents=True, exist_ok=True)
        manifesto.write_text(json.dumps(m.build(tools, m.politica_padrao())), encoding="utf-8")
        dados = self.perfil(tipo=EX.FERRAMENTAS_DE_TERCEIROS,
                            codigo={"preso": True, "raiz": "tools",
                                    "manifesto": "outputs/execucao/manifesto-tools.json",
                                    "manifesto_sha256": hashlib.sha256(manifesto.read_bytes()).hexdigest()},
                            montagens={"somente_leitura": ["alvos"], "saida": "outputs/execucao/saida"},
                            modelos=[{"nome": "roda", "argv": ["./run.sh", "{caminho}", "--saida={saida}"]}])
        argv = ["./run.sh", self.alvos / "um.txt", "--saida=" + str(self.saida / "r.txt")]
        r, res = self.rodar(dados, *argv)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ALVO-UM", res["stdout"])
        self.assertEqual((self.saida / "r.txt").read_text(encoding="utf-8"), "gerado\n")
        self.programa("run.sh", 'echo trocado > "${2#--saida=}"\n', tools)
        r, _res = self.rodar(dados, *argv)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("manifesto", erro_de(r))
        self.assertEqual((self.saida / "r.txt").read_text(encoding="utf-8"), "gerado\n", "o código trocado rodou")


class TestDeOndeVemOSha256(unittest.TestCase):
    """Integração final da 1.7.10, item I24: a ajuda do `rodar --perfil-sha256` dava o SHA-256 como "o da ficha de
    aberturas", a docstring dizia que "o aceite da ficha de aberturas prende o arquivo exato", e a descrição e a
    docstring chamavam o perfil de assinado; a seção `execucao` da ficha é da 1.7.11. Hoje o SHA-256 vem do
    `conferir-perfil`, aprovado pelo titular: os textos dizem isso, e toda frase deles que fala da ficha ou de
    assinatura diz que é da 1.7.11."""

    def sem_promessa(self, texto: str) -> None:
        for frase in " ".join(texto.split()).split(". "):
            if "ficha" in frase or "assinad" in frase:
                self.assertIn("1.7.11", frase, "promete a ficha (ou a assinatura) do perfil nesta versão")

    def ajuda(self, *args) -> str:
        r = cli(*args, "--help", env={**ENV, "COLUMNS": "2000"})  # sem quebra de linha no meio do texto
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_ajuda_do_perfil_sha256_diz_de_onde_vem_o_hash_hoje(self):
        ajuda = " ".join(self.ajuda("rodar").split())
        sha256 = ajuda.rsplit("--perfil-sha256 PERFIL_SHA256", 1)[1].split("--projeto", 1)[0]  # a linha da opção
        for termo in ("conferir-perfil", "titular", "execucao da ficha de aberturas", "1.7.11"):
            self.assertIn(termo, sha256)
        self.assertNotIn("(o da ficha de aberturas)", sha256)  # o texto de antes
        self.sem_promessa(ajuda)
        self.sem_promessa(self.ajuda())

    def test_docstring_e_uso_nao_prometem_a_ficha(self):
        doc = " ".join(EX.__doc__.split())
        uso = doc.split("pela linha de comando:", 1)[1].split(" O perfil (", 1)[0]
        self.assertIn("rodar --perfil <arq> --perfil-sha256 <h>", uso)
        for termo in ("O `<h>` é o SHA-256", "`conferir-perfil` mostra", "1.7.11"):
            self.assertIn(termo, uso)
        self.assertNotIn("o aceite da ficha de aberturas prende", doc)
        self.sem_promessa(doc)


class TestFolhaERecusaSemPromessa(_Projeto):
    """Revisão da terceira rodada da integração, defeito 3 (a I24 pela metade): a folha que o `conferir-perfil` mostra
    ao titular, o texto que ele lê para aprovar, dizia que o perfil vale pela ficha de aberturas ("execucao[] {perfil,
    sha256}") e pelo aceite assinado dela, e a recusa do SHA-256 diferente mandava pedir novo aceite da ficha; na 1.7.10
    a seção `execucao` da ficha é reservada (preenchida, a ficha é recusada com "1.7.11") e o `rodar` aceita o SHA-256
    que o titular aprovou. Os dois textos, a docstring e as do módulo do perfil dizem isso: toda frase deles que fala da
    ficha ou de assinatura diz que é da 1.7.11 (`TestDeOndeVemOSha256.sem_promessa`)."""

    def sem_promessa(self, texto: str) -> None:
        TestDeOndeVemOSha256.sem_promessa(self, texto)

    def test_folha_do_conferir_perfil_diz_que_o_titular_aprova_o_sha256(self):
        arquivo, sha = self.gravar(self.perfil())
        r = cli("conferir-perfil", "--perfil", arquivo, "--projeto", "p")
        self.assertEqual(r.returncode, 0, r.stderr)
        folha = json.loads(r.stdout)["para_a_folha"]
        self.sem_promessa(folha)
        for termo in (f"SHA-256 do perfil: {sha}", "você aprova este SHA-256 na folha de decisões",
                      "seção execucao da ficha de aberturas", "1.7.11"):
            self.assertIn(termo, folha)
        for velho in ("execucao[]", "assina o aceite da ficha", "entra na ficha"):  # o texto de antes
            self.assertNotIn(velho, folha)

    def test_recusa_do_sha256_diferente_pede_nova_aprovacao(self):
        arquivo, sha = self.gravar(self.perfil())
        with self.assertRaises(EX.Recusa) as ctx:
            EX.ler_perfil(arquivo, "0" * 64)
        texto = str(ctx.exception)
        self.sem_promessa(texto)
        for termo in (f"tem {sha}", "o SHA-256 aprovado prende o arquivo exato", "conferir-perfil", "nova aprovação"):
            self.assertIn(termo, texto)
        self.assertNotIn("ficha", texto)  # antes: "o aceite da ficha de aberturas prende o arquivo exato"

    def test_docstrings_do_modulo_do_perfil(self):
        arvore = ast.parse((SCRIPTS / "perfil_execucao.py").read_text(encoding="utf-8"))
        doc = ast.get_docstring(arvore)
        self.assertTrue(doc.startswith("Perfil de execução aprovado pelo SHA-256"), doc[:80])  # antes: "assinado"
        funcoes = {n.name: ast.get_docstring(n) for n in arvore.body if isinstance(n, ast.FunctionDef)}
        for nome in ("ler_perfil", "folha_do_perfil", "conferir_perfil"):
            with self.subTest(nome):
                self.sem_promessa(funcoes[nome])
        self.sem_promessa(doc)


if __name__ == "__main__":
    unittest.main()
