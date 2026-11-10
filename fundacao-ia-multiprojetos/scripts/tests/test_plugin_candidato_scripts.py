"""Skills com scripts no scripts/plugin_candidato.py (1.7.11, lote S1; desenho de skills e agentes, §3.1, §3.2 e §4.4).

Com `--com-scripts`, o `montar`, o `conferir` e o `revisar` aceitam `skills/<s>/scripts/<arquivo>.py` e o
`skills/<s>/requirements.lock`; sem a opção, tudo fica como era (o `.py` recusa, com a dica). Provas:
- positiva: o candidato conforme traz a sugestão `skills_com_scripts_para_a_ficha`, que o validador da ficha e o kit aceitam;
- negativas: `#!`, outras linguagens, `.py` fora do lugar, nome fora da forma, texto com controle, direção ou codificação
  que não é utf-8, lock fora da forma ou sem a linha `# rodas:`, `__pycache__`, e o `.py` sem a opção;
- `travar`: o lock sai das rodas (`.whl`) do projeto, com o SHA-256 de cada uma; recusa o que não é roda, a versão dupla,
  a pasta fora do projeto, em data/ ou no candidato, a skill que não existe e o candidato fora de plugins-candidatos/;
- `revisar`: a seção "Código que roda" (importações e marcas lidas pela árvore sintática, sem executar nada), a lista de
  pacotes do lock e a caixa de aceite;
- registro: o aviso da skill cujo nome está nas negações do registro da raiz, se ele for legível.
Pastas descartáveis com dados fictícios; nenhum script nem roda é importado ou executado.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

from apoio import KIT, SCRIPTS, criar_ligacao_dir
from test_plugin_candidato import MOD, Fundacao, escrever, rodar
from test_plugin_regra_unica_1710 import ficha_com

if str(KIT) not in sys.path:  # o kit desta skill, pelo caminho (o mesmo que a ferramenta do titular carrega)
    sys.path.insert(0, str(KIT))
from fundacao.core import aberturas_plugins as plugins  # noqa: E402
from fundacao.core import aberturas_regras as regras  # noqa: E402
from fundacao.core import aberturas_scripts as lock_do_kit  # noqa: E402

SCRIPT = "import json\nprint(json.dumps({'ok': True}))\n"
SKILL_BUSCA = "---\nname: busca\ndescription: Busca (skill fictícia).\n---\n\nChame o executor da fundação.\n"
CAMINHO = "skills/busca/scripts/buscar.py"
RODAS = "outputs/rodas-busca-20261108"
RODAS_DO_TESTE = {"alfa-1.0-py3-none-any.whl": b"roda alfa", "Beta_Pacote-2.1.post1-cp312-cp312-win_amd64.whl": b"beta win",
                  "beta_pacote-2.1.post1-cp312-cp312-manylinux_2_17_x86_64.whl": b"beta linux"}
MARCAS = ("import os\nimport subprocess\nimport urllib.request\n\nURL = 'https://exemplo.invalid/api'\n"
          "os.system('ls')\nopen('saida.txt', 'w').write(eval('1+1') and 'x')\nPASTA = '/etc/passwd'\n"
          "__import__('socket')\n")


def lock_de(nomes_e_hashes: dict) -> str:
    return f"# rodas: {RODAS}\n" + "".join(
        f"{nome}=={versao} \\\n" + " \\\n".join(f"    --hash=sha256:{h}" for h in sorted(hashes)) + "\n"
        for nome, (versao, hashes) in sorted(nomes_e_hashes.items()))


def sha(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


class Base(Fundacao):
    def candidato_com_scripts(self, extras: dict | None = None, nome: str = "demo-kit") -> Path:
        arquivos = {"skills/busca/SKILL.md": SKILL_BUSCA, CAMINHO: SCRIPT}
        return self.candidato({**arquivos, **(extras or {})}, nome=nome)

    def conferir(self, pasta, **kw) -> dict:
        return MOD.conferir(pasta, com_scripts=True, **kw)

    def recusado(self, pasta, trecho: str) -> dict:
        res = self.conferir(pasta)
        self.assertFalse(res["conforme"], f"devia recusar {pasta.name}")
        self.assertIsNone(res["manifesto_sha256"])
        self.assertTrue(any(trecho in m for m in res["motivos"]), f"{trecho!r} não está em {res['motivos']}")
        return res

    def rodas(self, arquivos: dict | None = None, pasta: str = RODAS) -> Path:
        destino = self.proj / pasta
        destino.mkdir(parents=True, exist_ok=True)
        escrever(destino, RODAS_DO_TESTE if arquivos is None else arquivos)
        return destino

    def item(self, pasta: Path, res: dict) -> dict:
        return {"nome": pasta.name, "origem": f"plugins-candidatos/{pasta.name}", "manifesto_sha256": res["manifesto_sha256"],
                "skills_com_scripts": res["skills_com_scripts_para_a_ficha"]}


class ConferirComScripts(Base, unittest.TestCase):
    def test_sem_a_opcao_o_py_recusa_com_a_dica_e_o_resto_fica_como_era(self):
        pasta = self.candidato_com_scripts()
        res = MOD.conferir(pasta)
        self.assertFalse(res["conforme"])
        self.assertTrue(any(CAMINHO in m and "1.7.11" in m and "--com-scripts" in m for m in res["motivos"]), res["motivos"])
        self.assertEqual((res["manifesto_sha256"], res["skills_com_scripts_para_a_ficha"]), (None, []))
        lock = self.candidato_com_scripts({"skills/busca/requirements.lock": "x"}, nome="demo-lock")
        self.assertFalse(MOD.conferir(lock)["conforme"])
        self.assertTrue(MOD.conferir(self.candidato(nome="demo-md"))["conforme"])  # o plugin de Markdown segue igual

    def test_com_a_opcao_o_candidato_conforme_traz_a_sugestao_que_o_kit_aceita(self):
        pasta = self.candidato_com_scripts()
        res = self.conferir(pasta)
        self.assertTrue(res["conforme"], res["motivos"])
        self.assertEqual(res["skills_com_scripts_para_a_ficha"], [{
            "skill": "busca", "skill_md_sha256": sha(SKILL_BUSCA.encode()), "scripts": [{
                "nome": "buscar", "caminho": CAMINHO, "sha256": sha(SCRIPT.encode()), "modo": "sessao"}]}])
        item = self.item(pasta, res)
        self.assertEqual(regras.validar(ficha_com(item), projeto="demo")["erros"], [])
        self.assertEqual(plugins.conferir_plugin(self.proj, item)["erros"], [])
        self.assertEqual(res["manifesto_sha256"], plugins.conferir_pasta_do_plugin(pasta, pasta.name,
                                                                                   item["skills_com_scripts"])["manifesto_sha256"])
        self.assertIsNone(plugins.conferir_pasta_do_plugin(pasta, pasta.name)["manifesto_sha256"])  # sem a lista, o kit recusa

    def test_nome_do_script_com_sublinhado_vira_hifen_na_ficha(self):
        pasta = self.candidato_com_scripts({"skills/busca/scripts/buscar_tudo.py": SCRIPT})
        nomes = [s["nome"] for s in self.conferir(pasta)["skills_com_scripts_para_a_ficha"][0]["scripts"]]
        self.assertEqual(nomes, ["buscar", "buscar-tudo"])

    def test_shebang_recusa_com_a_instrucao(self):
        pasta = self.candidato_com_scripts({CAMINHO: "#!/usr/bin/env python3\n" + SCRIPT})
        self.recusado(pasta, "tire a primeira linha #!: o executor chama o interpretador")

    def test_py_fora_do_lugar_e_outras_linguagens_recusam(self):
        for rel in ("skills/busca/buscar.py", "skills/busca/scripts/sub/buscar.py", "skills/busca/scripts/Coletar.py",
                    "skills/busca/scripts/__init__.py", "skills/busca/scripts/coletar.PY", "agents/coletar.py",
                    "commands/coletar.py", "skills/busca/scripts/coletar.sh", "skills/busca/scripts/coletar.js",
                    "skills/busca/scripts/coletar.pyc", "skills/busca/scripts/coletar.ps1", "skills/busca/scripts/coletar.exe",
                    "skills/busca/scripts/__pycache__/coletar.pyc", "skills/busca/venv/coletar.py",
                    "skills/busca/scripts/coletar.py.txt", "scripts/coletar.py", "hooks/coletar.py"):
            with self.subTest(rel=rel):
                res = self.conferir(self.candidato_com_scripts({rel: "print(1)\n"}))
                self.assertFalse(res["conforme"], rel)
                self.assertTrue(any(m.startswith(rel.split("/")[0]) for m in res["motivos"]), res["motivos"])

    def test_texto_do_py_com_controle_direcao_ou_codificacao_recusa(self):
        casos = {"x = '" + chr(0x202e) + "'\n": "controle", "x = 1\ry = 2\n": "CR sozinho", "x = 1\x00\n": "controle",
                 "# coding: latin-1\n" + SCRIPT: "só utf-8", "# coding=utf-7\n": "só utf-8", b"\xff\xfe": "UTF-8",
                 b"\x7fELF\x02\x01": "ELF", b"MZ texto\n": "executável", "x = 1\n" * 90000: "teto",
                 SCRIPT + chr(0xFEFF): "U+FEFF"}
        for texto, trecho in casos.items():
            with self.subTest(texto=str(texto)[:30]):
                res = self.conferir(self.candidato_com_scripts({CAMINHO: texto}))
                self.assertFalse(res["conforme"])
                self.assertTrue(any(CAMINHO in m for m in res["motivos"]), res["motivos"])
        self.assertTrue(self.conferir(self.candidato_com_scripts({CAMINHO: "# coding: utf-8\n" + SCRIPT}))["conforme"])

    def test_lock_sem_a_linha_de_rodas_ou_fora_da_forma_recusa(self):
        bom = lock_de({"alfa": ("1.0", {"a" * 64})})
        self.assertTrue(self.conferir(self.candidato_com_scripts({"skills/busca/requirements.lock": bom}))["conforme"])
        casos = {bom.split("\n", 1)[1]: "sem a linha '# rodas:", "# rodas: x\n-e .\n": "opção de pip",
                 "# rodas: x\nalfa==1.0\n": "sem --hash", "# rodas: x\nalfa @ https://x.example/a.whl\n": "URL",
                 "# rodas: x\n": "lock sem pacote"}
        for texto, trecho in casos.items():
            with self.subTest(trecho=trecho):
                self.recusado(self.candidato_com_scripts({"skills/busca/requirements.lock": texto}), trecho)

    def test_lock_de_skill_sem_script_nem_dono_recusa(self):
        pasta = self.candidato_com_scripts({"skills/ola/requirements.lock": lock_de({"alfa": ("1.0", {"a" * 64})})})
        res = self.conferir(pasta)
        self.assertFalse(res["conforme"], "o lock da skill sem script não tem item na ficha")

    def test_sugestao_leva_as_dependencias_quando_o_lock_traz_a_linha_de_rodas(self):
        lock = lock_de({"alfa": ("1.0", {"a" * 64}), "beta": ("2", {"b" * 64, "c" * 64})})
        pasta = self.candidato_com_scripts({"skills/busca/requirements.lock": lock})
        res = self.conferir(pasta)
        self.assertTrue(res["conforme"], res["motivos"])
        dep = res["skills_com_scripts_para_a_ficha"][0]["dependencias"]
        self.assertEqual(dep, {"lock": "skills/busca/requirements.lock", "lock_sha256": sha(lock.encode()), "rodas": RODAS,
                               "python": "3.12", "pacotes": 2})
        item = self.item(pasta, res)
        self.assertEqual(regras.validar(ficha_com(item), projeto="demo")["erros"], [])
        self.assertEqual(plugins.conferir_plugin(self.proj, item)["erros"], [])
        pasta.joinpath(CAMINHO).write_text(SCRIPT + "# depois da assinatura\n", encoding="utf-8")
        self.assertTrue(plugins.conferir_plugin(self.proj, item)["erros"])  # script trocado: o kit recusa


class MontarComScripts(Base, unittest.TestCase):
    def origem_com_scripts(self, extras: dict | None = None) -> Path:
        origem = self.proj / "importado" / "busca"
        escrever(origem, {"SKILL.md": SKILL_BUSCA, "scripts/buscar.py": SCRIPT, **(extras or {})})
        return origem

    def test_montar_copia_o_script_e_devolve_a_sugestao_e_os_passos_com_a_opcao(self):
        res = MOD.montar(self.raiz, "demo", "busca", self.origem_com_scripts(), com_scripts=True)
        destino = Path(res["candidato"])
        self.assertEqual((destino / CAMINHO).read_text(encoding="utf-8"), SCRIPT)
        self.assertEqual(res["skills_com_scripts_para_a_ficha"][0]["scripts"][0]["caminho"], CAMINHO)
        self.assertTrue(all("--com-scripts" in p for p in res["proximos_passos"][:2]), res["proximos_passos"])
        self.assertEqual(set(res["ficha"]), {"nome", "origem", "manifesto_sha256"})
        self.assertEqual(res["manifesto_sha256"], plugins.conferir_pasta_do_plugin(
            destino, destino.name, res["skills_com_scripts_para_a_ficha"])["manifesto_sha256"])
        if os.name != "nt":
            self.assertEqual(oct((destino / CAMINHO).stat().st_mode & 0o777), oct(0o444))

    def test_montar_sem_a_opcao_ou_com_shebang_ou_com_shell_recusa_e_nao_deixa_nada(self):
        casos = {"sem a opção": ({}, False, "--com-scripts"),
                 "com #!": ({"scripts/buscar.py": "#!/usr/bin/env python3\n" + SCRIPT}, True, "tire a primeira linha #!"),
                 "com shell": ({"scripts/rodar.sh": "echo ficticio\n"}, True, "1.7.11"),
                 "com pycache": ({"scripts/__pycache__/buscar.pyc": "x"}, True, "__pycache__")}
        for nome, (extras, com, trecho) in casos.items():
            with self.subTest(caso=nome):
                with self.assertRaises(MOD.CandidatoRecusado) as ctx:
                    MOD.montar(self.raiz, "demo", "busca", self.origem_com_scripts(extras), com_scripts=com)
                self.assertIn(trecho, " ".join(ctx.exception.motivos))
                self.assertFalse((self.proj / "plugins-candidatos" / "demo-busca").exists())
                self.assertEqual([p.name for p in (self.proj / "plugins-candidatos").glob(".montando-*")]
                                 if (self.proj / "plugins-candidatos").exists() else [], [])

    def test_pela_linha_de_comando(self):
        origem = self.origem_com_scripts()
        r = rodar("montar", "--raiz", self.raiz, "--projeto", "demo", "--nome", "busca", "--origem", origem, "--com-scripts")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        destino = self.proj / "plugins-candidatos" / "demo-busca"
        self.assertEqual(rodar("conferir", "--pasta", destino).returncode, 2)
        c = rodar("conferir", "--pasta", destino, "--com-scripts")
        self.assertEqual(c.returncode, 0, c.stdout + c.stderr)
        self.assertEqual(json.loads(c.stdout)["skills_com_scripts_para_a_ficha"][0]["skill"], "busca")


class TravarAsRodas(Base, unittest.TestCase):
    def travar(self, **kw) -> dict:
        pasta = kw.pop("pasta", None) or self.candidato_com_scripts()
        return MOD.travar(pasta, kw.pop("skill", "busca"), kw.pop("rodas", RODAS))

    def test_o_lock_sai_das_rodas_com_o_sha256_de_cada_uma_e_o_candidato_confere(self):
        self.rodas()
        pasta = self.candidato_com_scripts()
        res = MOD.travar(pasta, "busca", RODAS)
        esperado = lock_de({"alfa": ("1.0", {sha(b"roda alfa")}),
                            "beta-pacote": ("2.1.post1", {sha(b"beta win"), sha(b"beta linux")})})
        lock = pasta / "skills" / "busca" / "requirements.lock"
        self.assertEqual(lock.read_text(encoding="utf-8"), esperado)
        self.assertEqual((res["pacotes"], res["rodas"], res["lock_sha256"]), (2, 3, sha(esperado.encode())))
        self.assertEqual(lock_do_kit.ler_lock(esperado.encode()), ([], ["alfa", "beta-pacote"]))
        conferido = self.conferir(pasta)
        self.assertTrue(conferido["conforme"], conferido["motivos"])
        self.assertEqual(conferido["skills_com_scripts_para_a_ficha"][0]["dependencias"]["rodas"], RODAS)
        item = self.item(pasta, conferido)
        self.assertEqual(regras.validar(ficha_com(item), projeto="demo")["erros"], [])
        self.assertEqual(plugins.conferir_plugin(self.proj, item)["erros"], [])

    def test_rodas_com_caminho_absoluto_do_projeto_e_travar_de_novo_troca_o_lock(self):
        destino = self.rodas()
        pasta = self.candidato_com_scripts()
        MOD.travar(pasta, "busca", destino)
        (destino / "gama-3.0-py3-none-any.whl").write_bytes(b"roda gama")
        res = MOD.travar(pasta, "busca", destino)
        self.assertEqual(res["pacotes"], 3)

    def test_o_que_nao_e_roda_recusa(self):
        casos = {"fonte": {"alfa-1.0.tar.gz": b"x"}, "texto": {"LEIAME.txt": b"x"}, "nome": {"alfa.whl": b"x"},
                 "nome com partes demais": {"a-1-2-3-4-5-6-7.whl": b"x"}, "versão sem dígito": {"a-x-py3-none-any.whl": b"x"},
                 "subpasta": {"sub/alfa-1.0-py3-none-any.whl": b"x"}, "nome maiúsculo": {"alfa-1.0-py3-none-any.WHL": b"x"}}
        for nome, arquivos in casos.items():
            with self.subTest(caso=nome):
                self.rodas(arquivos, pasta=f"outputs/rodas-{len(nome)}")
                pasta = self.candidato_com_scripts()
                with self.assertRaises(MOD.CandidatoRecusado):
                    MOD.travar(pasta, "busca", f"outputs/rodas-{len(nome)}")
                self.assertFalse((pasta / "skills" / "busca" / "requirements.lock").exists())

    def test_versao_dupla_pasta_vazia_e_teto_recusam(self):
        pasta = self.candidato_com_scripts()
        self.rodas({"alfa-1.0-py3-none-any.whl": b"1", "alfa-2.0-py3-none-any.whl": b"2"}, pasta="outputs/dupla")
        with self.assertRaises(MOD.CandidatoRecusado) as ctx:
            MOD.travar(pasta, "busca", "outputs/dupla")
        self.assertIn("duas versões de alfa", " ".join(ctx.exception.motivos))
        (self.proj / "outputs" / "vazia").mkdir()
        with self.assertRaises(MOD.CandidatoRecusado):
            MOD.travar(pasta, "busca", "outputs/vazia")
        self.rodas({"alfa-1.0-py3-none-any.whl": b"123456"}, pasta="outputs/grande")
        with mock.patch.dict(MOD.TETO_RODAS, {"bytes_roda": 5}), self.assertRaises(MOD.CandidatoRecusado) as ctx:
            MOD.travar(pasta, "busca", "outputs/grande")
        self.assertIn("teto", " ".join(ctx.exception.motivos))

    def test_pasta_das_rodas_fora_do_projeto_em_data_ou_no_candidato_recusa(self):
        self.rodas()
        (self.proj / "data" / "rodas").mkdir(parents=True)
        pasta = self.candidato_com_scripts()
        for rodas in ("../outro", "data/rodas", "plugins-candidatos", "plugins-candidatos/demo-kit", str(self.base),
                      str(self.outro), "outputs/nao-existe", "outputs/rodas com espaço", "."):
            with self.subTest(rodas=rodas):
                with self.assertRaises(MOD.CandidatoRecusado):
                    MOD.travar(pasta, "busca", rodas)

    def test_skill_inexistente_ou_fora_da_forma_e_candidato_fora_do_lugar_recusam(self):
        self.rodas()
        pasta = self.candidato_com_scripts()
        for skill in ("nao-existe", "Busca", "../busca", "", "ola/x"):
            with self.subTest(skill=skill), self.assertRaises(MOD.CandidatoRecusado):
                MOD.travar(pasta, skill, RODAS)
        with self.assertRaises(MOD.CandidatoRecusado) as sem_script:  # a skill ola é só Markdown
            MOD.travar(pasta, "ola", RODAS)
        self.assertIn("sem skills/ola/scripts/*.py", " ".join(sem_script.exception.motivos))
        solto = self.base / "solto"
        solto.mkdir()
        with self.assertRaises(MOD.CandidatoRecusado) as ctx:
            MOD.travar(solto, "busca", RODAS)
        self.assertIn("plugins-candidatos", " ".join(ctx.exception.motivos))
        with mock.patch.dict(os.environ, {"FUNDACAO_" + "PROJECT": "outro"}), self.assertRaises(MOD.CandidatoRecusado):
            MOD.travar(pasta, "busca", RODAS)  # a sessão de outro projeto não trava o candidato deste

    def test_roda_que_e_ligacao_recusa(self):
        destino = self.rodas({"alfa-1.0-py3-none-any.whl": b"x"})
        fora = self.base / "fora"
        fora.mkdir()
        criar_ligacao_dir(destino / "beta-1.0-py3-none-any.whl", fora)
        with self.assertRaises(MOD.CandidatoRecusado):
            MOD.travar(self.candidato_com_scripts(), "busca", RODAS)

    def test_pela_linha_de_comando(self):
        self.rodas()
        pasta = self.candidato_com_scripts()
        r = rodar("travar", "--pasta", pasta, "--skill", "busca", "--rodas", RODAS)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["pacotes"], 2)
        self.assertIn("--com-scripts", json.loads(r.stdout)["proximos_passos"][0])
        ruim = rodar("travar", "--pasta", pasta, "--skill", "busca", "--rodas", "data/x")
        self.assertEqual(ruim.returncode, 2)


class RevisarOCodigoQueRoda(Base, unittest.TestCase):
    def test_secao_com_as_marcas_sem_executar_nada(self):
        pasta = self.candidato_com_scripts({CAMINHO: MARCAS, "skills/busca/scripts/limpo.py": SCRIPT})
        texto, res = MOD.revisar(pasta, com_scripts=True)
        self.assertTrue(res["conforme"], res["motivos"])
        secao = texto.split("### Código que roda", 1)[1].split("## 3. Rede", 1)[0]
        for marca in ("`skills/busca/scripts/buscar.py`", "modo sugerido `sessao`", "`subprocess`", "`urllib`",
                      "importa: ", "`os`", "chamada(s) os.system", "eval/exec/compile: 1", "importação dinâmica: 1",
                      "escreve arquivos: 1 chamada(s)", "`exemplo.invalid`", "/etc/passwd", "tem marca de rede",
                      "PROGRAMAS", "a mesma autoridade dos comandos da sessão", "não julgam"):
            self.assertIn(marca, secao)
        limpo = secao.split("`skills/busca/scripts/limpo.py`", 1)[1]
        self.assertIn("marcas: nenhuma", limpo)
        self.assertIn("candidato ao modo `caixa`", limpo)
        self.assertNotIn("O plugin não leva script nem executável", texto)
        self.assertIn("aceito abri-los", texto)
        self.assertEqual(MOD.manifesto(pasta)[1], res["manifesto_sha256"])  # a revisão só lê

    def test_sintaxe_ilegivel_ou_funda_demais_nao_derruba_a_revisao(self):
        for texto in ("def x(:\n", "(" * 5000 + ")" * 5000 + "\n", "x = " + "[" * 400 + "]" * 400 + "\n"):
            with self.subTest(texto=texto[:20]):
                revisao, res = MOD.revisar(self.candidato_com_scripts({CAMINHO: texto}), com_scripts=True)
                self.assertTrue(res["conforme"], res["motivos"])
                self.assertIn("a sintaxe não foi lida", revisao)

    def test_lista_de_pacotes_do_lock_e_o_aviso_fixo(self):
        lock = lock_de({"alfa": ("1.0", {"a" * 64}), "beta-pacote": ("2.1", {"b" * 64})})
        texto, _res = MOD.revisar(self.candidato_com_scripts({"skills/busca/requirements.lock": lock}), com_scripts=True)
        self.assertIn("Pacotes do requirements.lock da skill `busca` (2)", texto)
        self.assertIn("- `alfa==1.0`", texto)
        self.assertIn("- `beta-pacote==2.1`", texto)
        self.assertIn("o hash prova que são os baixados, não que são seguros", texto)
        self.assertNotIn("a" * 64, texto)  # só o começo do hash da skill; o do pacote nem entra

    def test_texto_do_script_so_aparece_entre_crases(self):
        hostil = "# <!-- esconde --> [x](javascript:alert(1)) https://exemplo.invalid/a|b\nimport os\n"
        texto, _res = MOD.revisar(self.candidato_com_scripts({CAMINHO: hostil}), com_scripts=True)
        secao = texto.split("### Código que roda", 1)[1].split("## 3. Rede", 1)[0]
        self.assertNotIn("<!--", secao)
        self.assertIn("`exemplo.invalid`", secao)

    def test_sem_scripts_a_revisao_de_antes_e_sem_a_opcao_o_candidato_recusado_aparece(self):
        texto, res = MOD.revisar(self.candidato())
        self.assertIn("O plugin não leva script nem executável (a conferência recusa).", texto)
        self.assertNotIn("Código que roda", texto)
        recusado, res = MOD.revisar(self.candidato_com_scripts())
        self.assertFalse(res["conforme"])
        self.assertIn("**RECUSADO**", recusado)
        self.assertNotIn("aceito abri-los", recusado)

    def test_pela_linha_de_comando_grava_a_revisao(self):
        pasta = self.candidato_com_scripts()
        saida = self.proj / "outputs" / "plugins" / "kit" / "REVISAO.md"
        r = rodar("revisar", "--pasta", pasta, "--saida", saida, "--com-scripts")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("### Código que roda", saida.read_text(encoding="utf-8"))


class RegistroDeSkillsNegadas(Base, unittest.TestCase):
    def registro(self, negadas: list, projetos=("outro",)) -> None:
        dados = {"schema_version": "fundacao.projetos_host/1", "projetos": {
            p: {"origens": [], "somente_leitura": [], "aninhadas_negadas": negadas} for p in projetos}}
        escrever(self.raiz, {"registry/projetos-host.json": json.dumps(dados)})

    def avisos(self, pasta) -> list:
        return [a for a in self.conferir(pasta)["avisos"] if "negadas do registro" in a]

    def test_skill_com_nome_negado_em_outro_projeto_avisa_sem_dizer_qual(self):
        pasta = self.candidato_com_scripts()
        self.assertEqual(self.avisos(pasta), [])  # sem registro legível, nada a dizer (o preparo confere)
        self.registro(["BUSCA", "ola-outra"])
        achados = self.avisos(pasta)
        self.assertEqual(len(achados), 1, achados)
        self.assertIn("'busca'", achados[0])
        self.assertIn("renomeie a skill no candidato", achados[0])
        self.assertNotIn("outro", achados[0].replace("renomeie", "").replace("outro projeto", ""))
        self.registro(["ola"])  # a skill de Markdown do mesmo candidato também
        self.assertEqual(len(self.avisos(pasta)), 1)

    def test_o_name_do_cabecalho_conta_e_o_nome_novo_nao_avisa(self):
        self.registro(["scrapling-juridico"])
        diferente = self.candidato_com_scripts({"skills/busca/SKILL.md": SKILL_BUSCA.replace("name: busca",
                                                                                           "name: scrapling-juridico")})
        self.assertEqual(len(self.avisos(diferente)), 1)
        self.assertEqual(self.avisos(self.candidato_com_scripts(nome="demo-novo")), [])

    def test_agente_com_nome_negado_avisa_pelo_name_e_pelo_arquivo(self):
        """Lote S2 (A3): `agentes_negados` do registro (esquema /2) também avisa; o /1 (sem a chave) não derruba; a skill
        e o agente cada um com a sua lista (o nome de skill negado não fecha agente, nem o inverso)."""
        agente = "---\nname: {}\ndescription: ensaio\ntools: Read\n---\nCorpo.\n"
        pasta = self.candidato_com_scripts({"agents/revisor.md": agente.format("revisor")}, nome="demo-agente")
        outro = self.candidato_com_scripts({"agents/revisor.md": agente.format("outro-nome")}, nome="demo-agente2")

        def avisos(p) -> list:
            return [a for a in self.conferir(p)["avisos"] if "agentes negados do registro" in a]

        self.registro(["busca"])  # /1: só skills negadas
        self.assertEqual(avisos(pasta), [])
        dados = {"schema_version": "fundacao.projetos_host/2", "projetos": {"outro": {
            "origens": [], "somente_leitura": [], "aninhadas_negadas": [], "agentes_negados": ["REVISOR"]}}}
        escrever(self.raiz, {"registry/projetos-host.json": json.dumps(dados)})
        achados = avisos(pasta)
        self.assertEqual(len(achados), 1, achados)
        self.assertIn("'revisor'", achados[0])
        self.assertIn("renomeie o agente", achados[0])
        self.assertEqual(len(avisos(outro)), 1)  # o name é outro, mas o arquivo agents/revisor.md se chama revisor
        dados["projetos"]["outro"].update(agentes_negados=["busca"], aninhadas_negadas=["revisor"])
        escrever(self.raiz, {"registry/projetos-host.json": json.dumps(dados)})
        self.assertEqual(avisos(pasta), [])  # skill negada não fecha agente, e agente negado não fecha skill
        self.assertEqual([a for a in self.conferir(pasta)["avisos"] if "negadas do registro" in a], [])

    def test_registro_ilegivel_grande_ou_ligacao_nao_derruba_nem_avisa(self):
        pasta = self.candidato_com_scripts()
        arquivo = self.raiz / "registry" / "projetos-host.json"
        for conteudo in ("{ruim", "[]", json.dumps({"projetos": {"x": 5}}), json.dumps({"projetos": {"x": {
                "aninhadas_negadas": [5, None, "busca" + " " * (300 << 10)]}}}), ""):
            with self.subTest(conteudo=conteudo[:20]):
                escrever(self.raiz, {"registry/projetos-host.json": conteudo})
                self.assertEqual(self.avisos(pasta), [])
        arquivo.unlink()
        alvo = self.base / "registro-de-fora.json"
        alvo.write_text(json.dumps({"projetos": {"x": {"aninhadas_negadas": ["busca"]}}}), encoding="utf-8")
        try:
            os.symlink(alvo, arquivo)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"link simbólico indisponível: {exc}")
        self.assertEqual(self.avisos(pasta), [])

    def test_o_aviso_vale_tambem_no_montar_e_no_conferir_sem_a_opcao(self):
        self.registro(["busca"])
        origem = self.proj / "importado" / "busca"
        escrever(origem, {"SKILL.md": SKILL_BUSCA})
        res = MOD.montar(self.raiz, "demo", "busca", origem)
        self.assertTrue([a for a in res["avisos"] if "negadas do registro" in a], res["avisos"])
        self.assertTrue([a for a in MOD.conferir(res["candidato"])["avisos"] if "negadas do registro" in a])


if __name__ == "__main__":
    unittest.main()
