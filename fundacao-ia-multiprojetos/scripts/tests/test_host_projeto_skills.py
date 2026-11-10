"""1.7.11, lote S2 (desenho de skills e agentes, §3.5, §4.4 e §5): o preparo do Ubuntu para skills com scripts.

O que o lote muda no preparo (`preparo_host.py` e `preparo_skills.py`), com a prova negativa de cada abertura:
- a ficha: `plugins[].skills_com_scripts` passa pelo preparo (validador do kit, sem réplica) e vai ao aberturas.json;
- N-HASH-1: um byte do script trocado depois da assinatura recusa o preparo, sem gravar nada, e a versão instalada fica;
- N-HASH-3: roda que mudou, que sobra ou que falta contra o `requirements.lock` recusa antes do pip (a cópia conferida
  também confere, na hora de copiar); pasta de rodas com ligação, pasta ou arquivo que não é roda recusa;
- a venv: montada SEM rede (`pip install --no-index --no-deps --only-binary --require-hashes`, a partir de `/`, ambiente
  mínimo, sobre a cópia root das rodas e do lock); falha do pip apaga a pasta; o interpretador e a árvore vão ao hashes.json;
- Python da ficha diferente do da máquina recusa com o comando do `travar`;
- N-SK-7: skill ou agente da ficha com nome negado no registro (de qualquer projeto) recusa com "renomeie";
- o `--skills-base` é só de ensaio, e o `preparar-wsl.sh` repassa o `--registrar-aninhadas` e a pasta do ensaio.
U com o pip simulado (`preparo_skills.rodar` trocado) em toda parte; os de instalação (U no Linux) só rodam no Linux; os L
usam o pip real e rodas de teste geradas aqui (mínimas, sem rede), só no Ubuntu com python3-venv. Dados fictícios.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
import zipfile
from pathlib import Path

from apoio import ENV
from test_host_projeto_apoio import ABERTURAS_FALSO, LINUX, carregar_preparo, ficha_de_ensaio, gravar_ficha_na_caixa, usuario_atual
from test_host_projeto_perfil import resultado_de_ensaio

PROJETO = "caso-real"
PLUGIN = "caso-real-busca"
CHAVE = f"{PLUGIN}:busca"
RODAS_REL = "outputs/rodas-ensaio-20261108"
SKILL_MD = "---\nname: busca\ndescription: ensaio\n---\nCorpo.\n"
SCRIPT = 'print("busca")\n'
AGENTE_MD = "---\nname: redator\ndescription: ensaio\ntools: Read, Grep\nmodel: sonnet\n---\nCorpo.\n"
SCRIPT_REL = "skills/busca/scripts/buscar.py"


def escrever(pasta: Path, rel: str, texto: str) -> None:
    alvo = pasta.joinpath(*rel.split("/"))
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text(texto, encoding="utf-8", newline="\n")


def gerar_roda(pasta: Path, dist: str, versao: str = "1.0", codigo: str = "VALOR = 'um'\n") -> Path:
    """Uma roda mínima (só Python, sem dependências) feita aqui: o que o pip real instala sem rede."""
    modulo, info = dist.replace("-", "_"), f"{dist.replace('-', '_')}-{versao}.dist-info"
    arquivos = {f"{modulo}/__init__.py": codigo, f"{info}/METADATA": f"Metadata-Version: 2.1\nName: {dist}\nVersion: {versao}\n",
                f"{info}/WHEEL": "Wheel-Version: 1.0\nGenerator: ensaio\nRoot-Is-Purelib: true\nTag: py3-none-any\n"}
    registro = "".join("%s,sha256=%s,%d\n" % (n, base64.urlsafe_b64encode(hashlib.sha256(c.encode()).digest()).rstrip(b"=").decode(),
                                              len(c.encode())) for n, c in arquivos.items()) + f"{info}/RECORD,,\n"
    pasta.mkdir(parents=True, exist_ok=True)
    roda = pasta / f"{modulo}-{versao}-py3-none-any.whl"
    with zipfile.ZipFile(roda, "w") as z:
        for nome, conteudo in {**arquivos, f"{info}/RECORD": registro}.items():
            z.writestr(zipfile.ZipInfo(nome, date_time=(2026, 1, 1, 0, 0, 0)), conteudo)  # sem a hora: a roda é sempre a mesma
    return roda


def lock_das(rodas, versao: str = "1.0") -> str:
    """O requirements.lock das rodas (um pacote por roda, com o SHA-256 do arquivo), na forma que o kit aceita."""
    blocos = [f"{r.name.split('-')[0].replace('_', '-')}=={versao} \\\n    --hash=sha256:{hashlib.sha256(r.read_bytes()).hexdigest()}\n"
              for r in rodas]
    return f"# rodas: {RODAS_REL}\n" + "".join(blocos)


def montar_plugin(proj: Path, m, rodas=(), nome: str = PLUGIN, script: str = SCRIPT, agente: str | None = None,
                  python: str = "3.12") -> dict:
    """O candidato em plugins-candidatos/ e o item `plugins[]` da ficha (com o lock quando há rodas)."""
    pasta = proj / "plugins-candidatos" / nome
    shutil.rmtree(pasta, ignore_errors=True)
    arquivos = {".claude-plugin/plugin.json": json.dumps({"name": nome, "version": "0.1.0"}),
                "skills/busca/SKILL.md": SKILL_MD, SCRIPT_REL: script}
    if rodas:
        arquivos["skills/busca/requirements.lock"] = lock_das(rodas)
    if agente:
        arquivos["agents/redator.md"] = agente
    for rel, texto in arquivos.items():
        escrever(pasta, rel, texto)
    manifesto = m.manifesto_de_arvore(pasta, pastas_ignoradas=(), sufixos_ignorados=())
    skill = {"skill": "busca", "skill_md_sha256": manifesto["skills/busca/SKILL.md"]["sha256"],
             "scripts": [{"nome": "buscar", "caminho": SCRIPT_REL, "sha256": manifesto[SCRIPT_REL]["sha256"],
                          "modo": "sessao"}]}
    if rodas:
        skill["dependencias"] = {"lock": "skills/busca/requirements.lock", "python": python, "pacotes": len(rodas),
                                 "lock_sha256": manifesto["skills/busca/requirements.lock"]["sha256"], "rodas": RODAS_REL}
    item = {"nome": nome, "origem": f"plugins-candidatos/{nome}", "manifesto_sha256": m.sha256_do_plugin(manifesto),
            "skills_com_scripts": [skill]}
    if agente:
        item["agentes"] = [{"nome": "redator", "sha256": manifesto["agents/redator.md"]["sha256"],
                            "ferramentas": ["Read", "Grep"], "modelo": "sonnet"}]
    return item


class PipFalso:
    """O `preparo_skills.rodar` de unidade: registra a chamada e cria o que o venv e o pip criariam."""

    def __init__(self, falha: bool = False):
        self.chamadas, self.falha = [], falha

    def __call__(self, argv, *, cwd="/", env=None, tempo=0):
        self.chamadas.append({"argv": [str(a) for a in argv], "cwd": cwd, "env": dict(env or {})})
        if "venv" in argv:
            venv = Path(argv[-1])
            escrever(venv, "pyvenv.cfg", "home = /usr/bin\n")
            escrever(venv, "bin/python", "binario de ensaio\n")
            escrever(venv, "lib/python3.12/site-packages/pip/__pycache__/x.pyc", "compilado\n")
            return 0, ""
        if "pip" in argv:
            if self.falha:
                return 1, "ERROR: THESE PACKAGES DO NOT MATCH THE HASHES FROM THE REQUIREMENTS FILE"
            escrever(Path(argv[0]).parent.parent, "lib/python3.12/site-packages/ensaio_um/__init__.py", "VALOR = 'um'\n")
            return 0, "Successfully installed ensaio-um-1.0"
        return 0, ""

    def do_pip(self) -> list:
        return [c for c in self.chamadas if "pip" in c["argv"]]


class Base(unittest.TestCase):
    def setUp(self):
        self.m = carregar_preparo()
        self.ps = self.m.preparo_skills()
        self.tmp = Path(tempfile.mkdtemp(prefix="skills-s2-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        falso = self.tmp / "bin-falso" / "python3.12"  # o interpretador de ensaio: o nome diz a versão
        falso.parent.mkdir()
        falso.write_bytes(b"interpretador de ensaio\n")
        patch = unittest.mock.patch.object(self.ps, "PYTHON", str(falso))
        patch.start()
        self.addCleanup(patch.stop)
        self.pip, self.rodar_de_verdade = PipFalso(), self.ps.rodar
        patch = unittest.mock.patch.object(self.ps, "rodar", self.pip)
        patch.start()
        self.addCleanup(patch.stop)
        self.proj, self.area, self.base = self.tmp / "projeto", self.tmp / "area", self.tmp / "skills"
        self.proj.mkdir()
        self.rodas = [gerar_roda(self.proj / RODAS_REL, "ensaio-um"), gerar_roda(self.proj / RODAS_REL, "ensaio-dois")]

    def plugin(self, **extra) -> dict:
        return montar_plugin(self.proj, self.m, self.rodas, **extra)

    def planejar(self, item=None, anterior=None) -> list:
        item = item or self.plugin()
        return self.ps.planejar(PROJETO, PLUGIN, item["skills_com_scripts"], self.proj, self.proj / item["origem"],
                                self.base, anterior or {}, self.m.SKILL)

    def copiar_plugin_para_a_area(self, item) -> None:
        destino = self.area / "plugins" / PLUGIN
        shutil.rmtree(destino, ignore_errors=True)
        shutil.copytree(self.proj / item["origem"], destino)


class FichaComScripts(unittest.TestCase):
    """A forma na ficha: o validador é o do kit; o preparo só leva o que o aberturas.json e o executor usam."""

    def setUp(self):
        self.m = carregar_preparo()

    def ab(self, plugin):
        return self.m.aberturas_da_ficha(resultado_de_ensaio(plugins=[plugin]), PROJETO)

    def item(self, **mudanca):
        s = {"skill": "busca", "skill_md_sha256": "a" * 64, "scripts": [
            {"nome": "buscar", "caminho": SCRIPT_REL, "sha256": "b" * 64, "modo": "sessao"}]}
        s.update(mudanca)
        return {"nome": PLUGIN, "origem": f"plugins-candidatos/{PLUGIN}", "manifesto_sha256": "c" * 64,
                "skills_com_scripts": [s]}

    def test_a_ficha_com_scripts_vale_e_o_preparo_leva_a_copia(self):
        item = self.item(dependencias={"lock": "skills/busca/requirements.lock", "lock_sha256": "d" * 64,
                                       "rodas": RODAS_REL, "python": "3.12", "pacotes": 2})
        ab = self.ab(item)
        self.assertTrue(ab["valida"], ab["motivo"])
        self.assertEqual(ab["plugins"][0]["skills_com_scripts"], item["skills_com_scripts"])
        self.assertIsNot(ab["plugins"][0]["skills_com_scripts"][0], item["skills_com_scripts"][0])
        self.assertNotIn("skills_com_scripts", self.ab({**item, "skills_com_scripts": []})["plugins"][0])

    def test_o_que_o_kit_recusa_fecha_tudo(self):
        ruins = {"modo caixa (lote S4)": self.item(scripts=[{"nome": "buscar", "caminho": SCRIPT_REL, "sha256": "b" * 64,
                                                             "modo": "caixa"}]),
                 "campo a mais no script": self.item(scripts=[{"nome": "buscar", "caminho": SCRIPT_REL, "sha256": "b" * 64,
                                                               "modo": "sessao", "args": "-x"}]),
                 "Python fora da lista medida": self.item(dependencias={
                     "lock": "skills/busca/requirements.lock", "lock_sha256": "d" * 64, "rodas": RODAS_REL,
                     "python": "3.11", "pacotes": 2}),
                 "rodas dentro de data/": self.item(dependencias={
                     "lock": "skills/busca/requirements.lock", "lock_sha256": "d" * 64, "rodas": "data/rodas",
                     "python": "3.12", "pacotes": 2})}
        for nome, item in ruins.items():
            with self.subTest(nome):
                self.assertFalse(self.ab(item)["valida"], nome)
        sem_prefixo = {**self.item(), "nome": "busca", "origem": "plugins-candidatos/busca"}
        self.assertFalse(self.ab(sem_prefixo)["valida"])
        self.assertFalse(self.ab({**self.item(), "hooks": []})["valida"])  # chave de plugin que o preparo não conhece

    def test_forma_do_preparo_recusa_sem_o_kit(self):
        ps = self.m.preparo_skills()
        for ruim in ("busca", [5], [{"skill": "busca"}], [{**self.item()["skills_com_scripts"][0], "extra": 1}],
                     [{**self.item()["skills_com_scripts"][0], "scripts": []}],
                     [{**self.item()["skills_com_scripts"][0], "dependencias": {"lock": "x"}}]):
            with self.subTest(ruim=str(ruim)[:50]):
                with self.assertRaises(self.m.EntradaInvalida):
                    ps.scripts_do_plugin(PLUGIN, ruim)
        self.assertEqual(ps.scripts_do_plugin(PLUGIN, None), [])


class RodasContraOLock(Base):
    def test_rodas_iguais_ao_lock_passam(self):
        plano = self.planejar()[0]
        self.assertEqual([r["nome"] for r in plano["dependencias"]["rodas"]],
                         ["ensaio_dois-1.0-py3-none-any.whl", "ensaio_um-1.0-py3-none-any.whl"])
        self.assertEqual(plano["interpretador"]["versao"], "3.12")
        self.assertEqual(plano["dependencias"]["raiz"].name, plano["dependencias"]["lock_sha256"][:12])

    def test_roda_trocada_sobrando_ou_faltando_recusa_antes_do_pip(self):  # N-HASH-3
        item = self.plugin()
        casos = {
            "roda trocada": lambda: gerar_roda(self.proj / "x", "ensaio-um", codigo="VALOR = 'outra'\n").replace(
                self.rodas[1].with_name("ensaio_um-1.0-py3-none-any.whl")),
            "roda sobrando": lambda: gerar_roda(self.proj / RODAS_REL, "ensaio-tres"),
            "roda em outra versão": lambda: gerar_roda(self.proj / RODAS_REL, "ensaio-dois", "2.0"),
            "roda faltando": lambda: self.rodas[0].unlink(),
            "arquivo que não é roda": lambda: escrever(self.proj / RODAS_REL, "LEIAME.txt", "x\n"),
            "pasta dentro": lambda: (self.proj / RODAS_REL / "sub").mkdir(),
        }
        for nome, estraga in casos.items():
            with self.subTest(nome):
                shutil.rmtree(self.proj / RODAS_REL, ignore_errors=True)
                self.rodas = [gerar_roda(self.proj / RODAS_REL, "ensaio-um"), gerar_roda(self.proj / RODAS_REL, "ensaio-dois")]
                estraga()
                with self.assertRaises(self.m.EntradaInvalida) as e:
                    self.planejar(item)
                self.assertRegex(str(e.exception), "rodas|roda|pasta")
        self.assertEqual(self.pip.chamadas, [])

    def test_ligacao_no_lugar_da_roda_ou_na_pasta_recusa(self):
        item = self.plugin()
        alvo = self.tmp / "fora.whl"
        alvo.write_bytes(self.rodas[0].read_bytes())
        self.rodas[0].unlink()
        try:
            self.rodas[0].symlink_to(alvo)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"link simbólico indisponível: {exc}")
        with self.assertRaises(self.m.EntradaInvalida):
            self.planejar(item)
        self.rodas[0].unlink()
        self.rodas[0].write_bytes(alvo.read_bytes())
        self.planejar(item)  # a pasta de volta ao normal passa
        (self.proj / RODAS_REL).rename(self.proj / "rodas-de-verdade")
        (self.proj / RODAS_REL).symlink_to(self.proj / "rodas-de-verdade", target_is_directory=True)
        with self.assertRaises(self.m.EntradaInvalida) as e:
            self.planejar(item)
        self.assertIn("ligação", str(e.exception))

    def test_lock_trocado_depois_da_ficha_recusa(self):
        item = self.plugin()
        lock = self.proj / item["origem"] / "skills" / "busca" / "requirements.lock"
        lock.write_text(lock.read_text(encoding="utf-8") + "# mudou\n", encoding="utf-8", newline="\n")
        with self.assertRaises(self.m.EntradaInvalida) as e:
            self.planejar(item)
        self.assertIn("prepare a ficha de novo", str(e.exception))

    def test_python_da_ficha_diferente_do_da_maquina_recusa_com_o_comando(self):
        item = self.plugin()
        outro = self.tmp / "bin-falso" / "python3.13"
        outro.write_bytes(b"outro\n")
        with unittest.mock.patch.object(self.ps, "PYTHON", str(outro)):
            with self.assertRaises(self.m.EntradaInvalida) as e:
                self.planejar(item)
        self.assertIn("3.13", str(e.exception))
        self.assertIn("plugin_candidato.py travar --skill busca --rodas", str(e.exception))


class NomeContraORegistro(Base):
    def registro(self, skills=(), agentes=()) -> dict:
        return {"projetos": {"outro": {"origens": [], "somente_leitura": [], "aninhadas_negadas": list(skills),
                                       "agentes_negados": list(agentes)}}}

    def conferir(self, registro, item=None) -> None:
        item = item or self.plugin(agente=AGENTE_MD)
        manifesto = self.m.manifesto_de_arvore(self.proj / item["origem"], pastas_ignoradas=(), sufixos_ignorados=())
        self.ps.conferir_nomes(PROJETO, PLUGIN, manifesto, self.proj / item["origem"], item.get("agentes", []), registro,
                               self.m.SKILL)

    def test_n_sk_7_skill_com_nome_negado_em_qualquer_projeto_recusa(self):
        self.conferir(self.registro(skills=["outra"], agentes=["outro"]))  # nomes novos passam
        for negada in ("busca", "BUSCA"):
            with self.subTest(negada):
                with self.assertRaises(self.m.EntradaInvalida) as e:
                    self.conferir(self.registro(skills=[negada]))
                self.assertIn("renomeie a skill 'busca'", str(e.exception))
                self.assertIn("caso-real-busca", str(e.exception))  # o exemplo leva o prefixo do projeto

    def test_o_name_do_cabecalho_conta_alem_do_nome_da_pasta(self):
        item = self.plugin()
        escrever(self.proj / item["origem"], "skills/busca/SKILL.md", SKILL_MD.replace("name: busca", "name: scrapling-juridico"))
        with self.assertRaises(self.m.EntradaInvalida) as e:
            self.conferir(self.registro(skills=["scrapling-juridico"]), item)
        self.assertIn("scrapling-juridico", str(e.exception))

    def test_agente_com_nome_negado_recusa_e_o_nome_de_skill_nao_vale_para_agente(self):
        with self.assertRaises(self.m.EntradaInvalida) as e:
            self.conferir(self.registro(agentes=["Redator"]))
        self.assertIn("renomeie o agente 'redator'", str(e.exception))
        self.conferir(self.registro(skills=["redator"], agentes=["busca"]))  # skill negada não fecha agente, nem o inverso

    def test_pelo_preparo_inteiro_a_recusa_nao_grava_nada(self):
        if not LINUX:
            self.skipTest("a instalação inteira é do Ubuntu")
        casos = {"skill": self.registro(skills=["busca"]), "agente": self.registro(agentes=["redator"])}
        for nome, registro in casos.items():
            with self.subTest(nome):
                caso = _caso_de_instalacao(self)
                item = montar_plugin(caso.proj, caso.m, [], agente=AGENTE_MD)
                gravar_ficha_na_caixa(caso.raiz, PROJETO, ficha_de_ensaio(PROJETO, 1, plugins=[item]))
                escrever(caso.raiz, "registry/projetos-host.json", json.dumps({
                    "schema_version": "fundacao.projetos_host/2", **registro}))
                caso.aprovar_canario()
                r = _instalar_cli(caso)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("renomeie", r.stdout)
                self.assertFalse((caso.base / "area" / "projetos").exists())


class LigacaoDaVenvSai(Base):
    r"""F12 da revisão final da 1.7.11: a decisão pura (só texto, sem disco), a mesma em qualquer sistema. O alvo com barra
    invertida ou `:` é recusado direto, sem trocar a barra: no Linux `a\b` é um nome de pasta, não duas."""

    def test_alvo_que_fica_dentro_da_venv_vale(self):
        for rel, alvo in (("bin/python3", "python3.12"), ("lib64", "lib"), ("bin/x", "../lib/y"), ("a/b/c", "../../d")):
            with self.subTest(rel=rel, alvo=alvo):
                self.assertFalse(self.ps.ligacao_da_venv_sai(rel, alvo))

    def test_alvo_que_sai_ou_que_a_conferencia_lexical_nao_garante_e_recusado(self):
        B = chr(92)
        casos = (("mau", ".." + B + "fora"), ("mau", "C:" + B + "x"), ("mau", "C:x"), ("mau", "c:/x"),
                 ("mau", B + B + "srv" + B + "x"), ("mau", B + "x"), ("mau", B + B + "?" + B + "C:" + B + "x"),
                 ("mau", "a" + B + "b/../../x"),  # o caso do F12: o código de c2fc71d aceitava no Linux
                 ("d1/mau", "a" + B + "b" + B + "c/../../../x"),
                 ("x", "l1/../../y"),  # `..` depois de segmento normal: a conferência não vê a ligação de pasta no meio
                 ("a/b/mau", "d/../../x"), ("mau", ""), ("mau", "/usr/bin/python3"),
                 ("x", "../fora"), ("bin/x", "../../fora"), ("mau", ".."), ("a/mau", "../.."))
        for rel, alvo in casos:
            with self.subTest(rel=rel, alvo=alvo):
                self.assertTrue(self.ps.ligacao_da_venv_sai(rel, alvo))


class ArvoreDaVenv(Base):
    def venv(self) -> Path:
        venv = self.tmp / "venv"
        escrever(venv, "pyvenv.cfg", "home = /usr/bin\n")
        escrever(venv, "lib/python3.12/site-packages/x/__init__.py", "X = 1\n")
        return venv

    def test_um_byte_mudado_ou_um_arquivo_a_mais_muda_a_soma(self):  # N-HASH-4 (a soma; o executor é do S3)
        venv = self.venv()
        base = self.ps.sha256_da_venv(self.ps.arvore_da_venv(venv))
        self.assertEqual(self.ps.sha256_da_venv(self.ps.arvore_da_venv(venv)), base)
        escrever(venv, "lib/python3.12/site-packages/x/__init__.py", "X = 2\n")
        mudada = self.ps.sha256_da_venv(self.ps.arvore_da_venv(venv))
        self.assertNotEqual(mudada, base)
        escrever(venv, "lib/python3.12/site-packages/x.pth", "import os\n")
        self.assertNotEqual(self.ps.sha256_da_venv(self.ps.arvore_da_venv(venv)), mudada)

    def test_ligacao_relativa_dentro_vale_e_a_que_sai_recusa(self):
        venv = self.venv()
        try:
            os.symlink("lib", venv / "lib64", target_is_directory=True)
            os.symlink("python", venv / "python3")
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"link simbólico indisponível: {exc}")
        arvore = self.ps.arvore_da_venv(venv)
        self.assertEqual(arvore["lib64"], {"ligacao": "lib"})
        for alvo in ("/usr/bin/python3", "../fora", "lib/../../fora"):
            with self.subTest(alvo):
                (venv / "mau").symlink_to(alvo)
                try:
                    with self.assertRaises(self.m.EntradaInvalida):
                        self.ps.arvore_da_venv(venv)
                finally:  # sem isto, uma falha deixava a ligação e o alvo seguinte quebrava com "já existe" (CI da 1.7.11)
                    (venv / "mau").unlink()

    def test_ligacao_com_barra_invertida_no_nome_da_pasta_recusa_so_no_posix(self):
        r"""F12: no Linux a pasta `a\b` existe (um nome só) e `a\b/../../x` sai da venv; o código antigo trocava a barra e
        aceitava. Onde o sistema não cria o nome ou a ligação, pula."""
        if os.name == "nt":
            self.skipTest("o Windows não cria pasta com barra invertida no nome")
        venv, B = self.venv(), chr(92)
        try:
            (venv / ("a" + B + "b")).mkdir()
            os.symlink("a" + B + "b/../../x", venv / "mau")
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"pasta ou link simbólico indisponível: {exc}")
        with self.assertRaises(self.m.EntradaInvalida):
            self.ps.arvore_da_venv(venv)

    def test_interpretador_real_com_hash_e_versao_pelo_nome_ou_pela_execucao(self):
        inter = self.ps.interpretador()
        self.assertEqual((inter["versao"], inter["sha256"]), ("3.12", hashlib.sha256(b"interpretador de ensaio\n").hexdigest()))
        sem_versao = self.tmp / "bin-falso" / "python3"
        sem_versao.write_bytes(b"sem versao no nome\n")
        with unittest.mock.patch.object(self.ps, "PYTHON", str(sem_versao)):
            with unittest.mock.patch.object(self.ps, "rodar", lambda *a, **k: (0, "3.12\n")):
                self.assertEqual(self.ps.interpretador()["versao"], "3.12")
            with unittest.mock.patch.object(self.ps, "rodar", lambda *a, **k: (1, "")):
                with self.assertRaises(self.m.EntradaInvalida):
                    self.ps.interpretador()


class MontagemDaVenv(Base):
    """Rodas para a área root pela cópia conferida e a venv sem rede (o pip simulado)."""

    def test_prazo_esgotado_do_pip_vira_falha_do_passo_e_nao_deixa_a_pasta(self):
        _item, plano = self.preparar()
        with unittest.mock.patch.object(self.ps.subprocess, "run", side_effect=subprocess.TimeoutExpired("pip", 1)):
            self.assertEqual(self.rodar_de_verdade(["pip"], tempo=1), (124, "prazo de 1 s esgotado"))
            with unittest.mock.patch.object(self.ps, "rodar", self.rodar_de_verdade):
                with self.assertRaises(self.m.EntradaInvalida) as e:
                    self.ps.construir(plano, self.area, False, {})
        self.assertIn("prazo de", str(e.exception))
        self.assertFalse(plano["dependencias"]["raiz"].exists())

    def preparar(self):
        item = self.plugin()
        self.copiar_plugin_para_a_area(item)
        return item, self.planejar(item)[0]

    def test_o_pip_roda_sem_rede_pela_copia_root_com_o_ambiente_minimo(self):
        _item, plano = self.preparar()
        acoes = self.ps.construir(plano, self.area, False, {})
        raiz = plano["dependencias"]["raiz"]
        pip = self.pip.do_pip()[0]
        for opcao in ("-I", "-B", "--no-index", "--no-deps", "--only-binary=:all:", "--require-hashes", "--no-compile",
                      "--no-cache-dir"):
            self.assertIn(opcao, pip["argv"])
        self.assertEqual(pip["argv"][pip["argv"].index("--find-links") + 1], str(raiz / "rodas"))
        self.assertEqual(pip["argv"][pip["argv"].index("-r") + 1],
                         str(self.area / "plugins" / PLUGIN / "skills" / "busca" / "requirements.lock"))
        self.assertEqual(pip["cwd"], "/")
        self.assertEqual(set(pip["env"]) - {"TMPDIR"}, set(self.ps.AMBIENTE))  # nada de proxy, casa nem PIP_INDEX_URL
        self.assertEqual(pip["env"]["PIP_CONFIG_FILE"], "/dev/null")
        self.assertEqual(sorted(p.name for p in (raiz / "rodas").iterdir()), [r["nome"] for r in plano["dependencias"]["rodas"]])
        self.assertFalse((raiz / "tmp").exists())
        venv = plano["dependencias"]["venv"]
        self.assertFalse(list(venv.rglob("__pycache__")))  # o que o pip compilou sai antes da soma
        self.assertEqual(plano["venv"]["sha256"], self.ps.sha256_da_venv(self.ps.arvore_da_venv(venv)))
        self.assertEqual(acoes[0]["acao"], "criar")
        self.assertIn("sem rede", acoes[0]["detalhe"])
        self.assertEqual(self.ps.registro_dos_hashes([plano])[CHAVE]["interpretador"]["versao"], "3.12")

    def test_n_hash_3_roda_trocada_entre_o_plano_e_a_copia_o_pip_nem_roda(self):
        _item, plano = self.preparar()
        self.rodas[0].write_bytes(self.rodas[0].read_bytes() + b"\0")
        with self.assertRaises(OSError):  # a cópia conferida: SHA-256 do lock
            self.ps.construir(plano, self.area, False, {})
        self.assertEqual(self.pip.chamadas, [])
        self.assertFalse(plano["dependencias"]["raiz"].exists())

    def test_falha_do_pip_apaga_a_pasta_e_diz_o_motivo(self):
        _item, plano = self.preparar()
        self.pip.falha = True
        with self.assertRaises(self.m.EntradaInvalida) as e:
            self.ps.construir(plano, self.area, False, {})
        self.assertIn("DO NOT MATCH THE HASHES", str(e.exception))
        self.assertFalse(plano["dependencias"]["raiz"].exists())
        self.assertIsNone(plano["venv"])

    def test_lock_da_copia_root_diferente_da_ficha_nao_monta(self):
        _item, plano = self.preparar()
        lock = self.area / "plugins" / PLUGIN / "skills" / "busca" / "requirements.lock"
        lock.write_text(lock.read_text(encoding="utf-8") + "# mudou\n", encoding="utf-8", newline="\n")
        with self.assertRaises(self.m.EntradaInvalida):
            self.ps.construir(plano, self.area, False, {})
        self.assertEqual(self.pip.chamadas, [])

    def test_igual_quando_a_arvore_confere_e_refaz_quando_um_arquivo_mudou(self):
        item, plano = self.preparar()
        self.ps.construir(plano, self.area, False, {})
        anterior = self.ps.registro_dos_hashes([plano])
        plano2 = self.planejar(item, anterior)[0]
        acoes = self.ps.construir(plano2, self.area, False, {})
        self.assertEqual([a["acao"] for a in acoes], ["igual"])
        self.assertEqual(len(self.pip.do_pip()), 1)  # o pip não rodou de novo
        self.assertEqual(plano2["venv"]["sha256"], plano["venv"]["sha256"])
        arquivo = plano["dependencias"]["venv"] / "lib" / "python3.12" / "site-packages" / "ensaio_um" / "__init__.py"
        arquivo.write_text("VALOR = 'mexido'\n", encoding="utf-8")
        plano3 = self.planejar(item, anterior)[0]
        self.assertEqual([a["acao"] for a in self.ps.construir(plano3, self.area, False, {})], ["refazer"])
        self.assertEqual(len(self.pip.do_pip()), 2)

    def test_duas_skills_com_o_mesmo_lock_montam_uma_venv_so(self):
        _item, plano = self.preparar()
        outra = {**plano, "chave": f"{PLUGIN}:outra", "skill": "outra", "venv": None}
        feitas = {}
        self.ps.construir(plano, self.area, False, feitas)
        self.assertEqual(self.ps.construir(outra, self.area, False, feitas), [])
        self.assertEqual(outra["venv"], plano["venv"])
        self.assertEqual(len(self.pip.do_pip()), 1)

    def test_limpar_so_tira_o_que_nenhuma_skill_da_ficha_usa(self):
        _item, plano = self.preparar()
        self.ps.construir(plano, self.area, False, {})
        pasta = self.base / PROJETO
        (pasta / PLUGIN / "antigo123456").mkdir()
        (pasta / "caso-real-saiu" / "xyz").mkdir(parents=True)
        acoes = self.ps.limpar_antigas(self.base, PROJETO, [plano])
        self.assertEqual(sorted(Path(a["caminho"]).name for a in acoes), ["antigo123456", "caso-real-saiu"])
        self.assertTrue(plano["dependencias"]["raiz"].is_dir())
        self.assertEqual(self.ps.limpar_antigas(self.base / "nao-existe", PROJETO, [plano]), [])


def _vigente_de_ensaio():
    """O `aberturas.vigente` de ensaio do apoio, sem carregar o pacote `fundacao` no processo (só um por processo)."""
    espaco: dict = {}
    exec(compile(ABERTURAS_FALSO, "aberturas_falso", "exec"), espaco)  # noqa: S102 - o substituto do próprio apoio
    return espaco["vigente"]


def _caso_de_instalacao(teste):
    from test_host_projeto_area import _Base
    caso = _Base("setUp")
    caso.setUp()
    teste.addCleanup(caso.tearDown)
    return caso


def _instalar_cli(caso, *extra, simular=False):
    from test_host_projeto_apoio import instalar
    return instalar(caso.skill, caso.raiz, caso.base, PROJETO, caso.claude, *extra, simular=simular)


@unittest.skipUnless(LINUX, "a área do titular é do Ubuntu (WSL2): instalar-projeto só roda no Linux. NÃO RODADO no Windows")
class InstalarComScriptsPipSimulado(unittest.TestCase):
    """A instalação inteira em ensaio (sem root), no processo do teste e com o pip simulado: aberturas.json, hashes.json,
    cópia root dos scripts, N-HASH-1 e o Python da máquina."""

    def setUp(self):
        self.caso = _caso_de_instalacao(self)
        c = self.caso
        self.ps = c.m.preparo_skills()
        falso = c.base / "bin-falso" / "python3.12"
        falso.parent.mkdir()
        falso.write_bytes(b"interpretador de ensaio\n")
        self.pip = PipFalso()
        for alvo, valor in (("PYTHON", str(falso)), ("rodar", self.pip)):
            patch = unittest.mock.patch.object(self.ps, alvo, valor)
            patch.start()
            self.addCleanup(patch.stop)
        self.rodas = [gerar_roda(c.proj / RODAS_REL, "ensaio-um"), gerar_roda(c.proj / RODAS_REL, "ensaio-dois")]
        c.aprovar_canario()
        (c.base / "tmp").mkdir(exist_ok=True)

    def ficha(self, item) -> None:
        gravar_ficha_na_caixa(self.caso.raiz, PROJETO, ficha_de_ensaio(PROJETO, 1, plugins=[item]))

    def instalar(self, **extra) -> dict:
        c = self.caso
        return c.m.instalar_projeto(
            simular=False, ensaio=True, raiz=c.raiz, projeto=PROJETO, titular="titular", claude=c.claude,
            claude_versao="2.1.302", claude_sha256=hashlib.sha256(c.claude.read_bytes()).hexdigest(), origem_hash="ensaio",
            perfil_windows="/mnt/c/Users/<usuario>", casa=str(c.base / "home"), usuario=usuario_atual(),
            area_raiz=str(c.base / "area"), bin_dir=str(c.base / "bin"), temp_base=str(c.base / "tmp"),
            sonda_interop_cmd=str(c.base / "sem-interop" / "cmd.exe"),
            sonda_interop_binfmt=str(c.base / "sem-interop" / "binfmt"), gerenciadas=str(c.base / "claude-code-gerenciado"),
            ferramenta_base=None, skills_base=str(c.base / "skills"), vigente=_vigente_de_ensaio(), **extra)

    def test_instala_scripts_aberturas_e_hashes_e_a_segunda_vez_nada_muda(self):
        c = self.caso
        item = montar_plugin(c.proj, c.m, self.rodas)
        self.ficha(item)
        rel = self.instalar()
        self.assertEqual([a["acao"] for a in rel["acoes"] if a["item"].startswith("venv:")], ["criar"])
        self.assertEqual(rel["skills"][0]["pacotes"], 2)
        self.assertTrue([a for a in rel["avisos"] if "pacotes de terceiros" in a and "não que são seguros" in a])
        instaladas = json.loads((c.area / "aberturas.json").read_text(encoding="utf-8"))
        self.assertEqual(instaladas["plugins"][0]["skills_com_scripts"], item["skills_com_scripts"])
        self.assertEqual(instaladas["skills"], [CHAVE])
        hashes = json.loads((c.area / "hashes.json").read_text(encoding="utf-8"))
        registro = hashes["skills"][CHAVE]
        self.assertEqual(registro["interpretador"]["versao"], "3.12")
        venv = Path(registro["venv"]["caminho"])
        self.assertEqual(venv.parent.parent.parent.parent.name, "skills")  # <skills>/<p>/<plugin>/<lock>/venv
        self.assertEqual(registro["venv"]["sha256"], self.ps.sha256_da_venv(self.ps.arvore_da_venv(venv)))
        copia = c.area / "plugins" / PLUGIN / SCRIPT_REL
        self.assertEqual(copia.read_text(encoding="utf-8"), SCRIPT)
        self.assertEqual(c.m.conferir_abertura(c.raiz, PROJETO, c.area)["problemas"], [])
        self.assertIn(f"{CHAVE}", json.loads((c.area / "settings.wsl.json").read_text(encoding="utf-8"))["env"][
            "FUNDACAO_SKILLS"])
        antes = (c.area / "hashes.json").read_bytes()
        rel2 = self.instalar()
        self.assertEqual([a["acao"] for a in rel2["acoes"] if a["item"].startswith("venv:")], ["igual"])
        self.assertEqual((c.area / "hashes.json").read_bytes(), antes)
        self.assertEqual(len(self.pip.do_pip()), 1)

    def test_n_hash_2_script_trocado_na_copia_root_a_abertura_recusa(self):
        c = self.caso
        self.ficha(montar_plugin(c.proj, c.m, []))
        self.instalar()
        self.assertEqual(c.m.conferir_abertura(c.raiz, PROJETO, c.area)["problemas"], [])
        copia = c.area / "plugins" / PLUGIN / SCRIPT_REL
        os.chmod(copia, 0o644)
        copia.write_text(SCRIPT + 'print("trocado")\n', encoding="utf-8", newline="\n")
        problemas = c.m.conferir_abertura(c.raiz, PROJETO, c.area)["problemas"]
        self.assertTrue([p for p in problemas if f"plugin:{PLUGIN}" in p and "mudou desde o preparo" in p], problemas)

    def test_n_hash_1_um_byte_do_script_depois_da_assinatura_recusa_sem_gravar_e_a_versao_fica(self):
        from test_host_projeto_area import fotografia
        c = self.caso
        self.ficha(montar_plugin(c.proj, c.m, self.rodas))
        self.instalar()
        antes = fotografia(c.base / "area", c.base / "skills", c.base / "bin")
        escrever(c.proj / "plugins-candidatos" / PLUGIN, SCRIPT_REL, SCRIPT + "# um byte a mais\n")
        with self.assertRaises(c.m.EntradaInvalida) as e:
            self.instalar()
        self.assertRegex(str(e.exception), "SHA-256 do script difere|manifesto")
        self.assertEqual(fotografia(c.base / "area", c.base / "skills", c.base / "bin"), antes)
        self.assertEqual(len(self.pip.do_pip()), 1)

    def test_roda_sobrando_ou_python_diferente_recusam_sem_criar_a_area(self):
        c = self.caso
        self.ficha(montar_plugin(c.proj, c.m, self.rodas))
        gerar_roda(c.proj / RODAS_REL, "ensaio-tres")
        with self.assertRaises(c.m.EntradaInvalida) as e:
            self.instalar()
        self.assertIn("sobra a roda", str(e.exception))
        (c.proj / RODAS_REL / "ensaio_tres-1.0-py3-none-any.whl").unlink()
        outro = c.base / "bin-falso" / "python3.13"
        outro.write_bytes(b"outro\n")
        with unittest.mock.patch.object(self.ps, "PYTHON", str(outro)):
            with self.assertRaises(c.m.EntradaInvalida) as e:
                self.instalar()
        self.assertIn("plugin_candidato.py travar", str(e.exception))
        self.assertFalse((c.base / "area" / "projetos").exists())
        self.assertEqual(self.pip.chamadas, [])

    def test_script_sem_pacotes_vale_so_com_o_interpretador(self):
        c = self.caso
        self.ficha(montar_plugin(c.proj, c.m, []))
        rel = self.instalar()
        self.assertEqual([a for a in rel["acoes"] if a["item"].startswith("venv:")], [])
        registro = json.loads((c.area / "hashes.json").read_text(encoding="utf-8"))["skills"][CHAVE]
        self.assertEqual((registro["interpretador"]["versao"], registro["venv"]), ("3.12", None))
        self.assertEqual(self.pip.chamadas, [])
        self.assertFalse((c.base / "skills").exists())

    def test_skills_base_e_so_de_ensaio(self):
        c = self.caso
        r = subprocess.run([sys.executable, "-I", "-B", str(c.skill / "assets" / "host" / "preparo_host.py"),
                            "instalar-projeto", "--raiz", str(c.raiz), "--projeto", PROJETO, "--titular", "titular",
                            "--claude", str(c.claude), "--claude-versao", "2.1.302", "--claude-sha256", "0" * 64,
                            "--origem-hash", "x", "--perfil-windows", "/mnt/c/Users/<usuario>", "--casa", "/tmp",
                            "--usuario", "ensaio", "--skills-base", "/tmp/skills"], capture_output=True, text=True,
                           env=ENV, timeout=120, stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("só para ensaio", r.stdout)


@unittest.skipUnless(LINUX and os.path.exists("/usr/bin/python3"), "o pip real só roda no Ubuntu. NÃO RODADO no Windows")
class InstalarComPipReal(unittest.TestCase):
    """L: o pip e o venv de verdade, com as rodas feitas aqui; sem rede (a pasta é a única fonte)."""

    def setUp(self):
        pronto = subprocess.run(["/usr/bin/python3", "-I", "-c", "import ensurepip, sys; sys.exit(0 if sys.version_info[:2] "
                                 "== (3, 12) else 3)"], capture_output=True, stdin=subprocess.DEVNULL, timeout=60)
        if pronto.returncode != 0:
            self.skipTest("precisa do Python 3.12 do sistema com python3-venv (a lista medida do kit)")
        self.caso = _caso_de_instalacao(self)
        c = self.caso
        self.rodas = [gerar_roda(c.proj / RODAS_REL, "ensaio-um"), gerar_roda(c.proj / RODAS_REL, "ensaio-dois", codigo="DOIS = 2\n")]
        c.aprovar_canario()
        gravar_ficha_na_caixa(c.raiz, PROJETO, ficha_de_ensaio(PROJETO, 1, plugins=[montar_plugin(c.proj, c.m, self.rodas)]))

    def test_monta_a_venv_sem_rede_e_importa_os_pacotes(self):
        c = self.caso
        rel = _instalar_cli(c)
        self.assertEqual(rel.returncode, 0, rel.stdout + rel.stderr)
        registro = json.loads((c.area / "hashes.json").read_text(encoding="utf-8"))["skills"][CHAVE]
        venv = Path(registro["venv"]["caminho"])
        r = subprocess.run([str(venv / "bin" / "python"), "-I", "-B", "-c", "import ensaio_um, ensaio_dois; "
                            "print(ensaio_um.VALOR, ensaio_dois.DOIS)"], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=60)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "um 2"), r.stdout + r.stderr)
        ps = c.m.preparo_skills()
        self.assertEqual(registro["venv"]["sha256"], ps.sha256_da_venv(ps.arvore_da_venv(venv)))
        self.assertEqual(registro["interpretador"]["caminho"], os.path.realpath("/usr/bin/python3"))
        self.assertFalse(list(venv.rglob("__pycache__")))
        self.assertEqual(c.m.conferir_abertura(c.raiz, PROJETO, c.area)["problemas"], [])
        igual = json.loads(_instalar_cli(c).stdout)
        self.assertEqual([a["acao"] for a in igual["acoes"] if a["item"].startswith("venv:")], ["igual"])

    def test_n_hash_3_roda_trocada_depois_da_assinatura_o_pip_nem_roda(self):
        c = self.caso
        self.rodas[0].write_bytes(self.rodas[0].read_bytes() + b"\0")
        r = _instalar_cli(c)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("rodas fora do lock", r.stdout)
        self.assertFalse((c.base / "area" / "skills-ensaio").exists())
        self.assertFalse((c.base / "area" / "projetos").exists())


class PrepararWslRepassa(unittest.TestCase):
    """O preparar-wsl.sh repassa o --registrar-aninhadas e leva a pasta das skills do ensaio (texto do script)."""

    def setUp(self):
        self.texto = (Path(__file__).resolve().parents[2] / "assets" / "host" / "wsl" / "preparar-wsl.sh").read_text(
            encoding="utf-8")

    def test_registrar_aninhadas_e_skills_base_chegam_ao_instalar_projeto(self):
        for trecho in ("--registrar-aninhadas) REGISTRAR_ANINHADAS=1; shift ;;",
                       'if [ "$REGISTRAR_ANINHADAS" = 1 ]; then args+=(--registrar-aninhadas); fi',
                       'args+=(--skills-base "$AREA_RAIZ/skills-ensaio")', "[--registrar-aninhadas]",
                       "/usr/local/lib/fundacao-ia/skills"):
            self.assertIn(trecho, self.texto)
        usos = [l for l in self.texto.splitlines() if "--registrar-aninhadas" in l and "args+=" in l]
        self.assertEqual(len(usos), 1)  # a mesma lista serve à simulação e à execução real


if __name__ == "__main__":
    unittest.main()
