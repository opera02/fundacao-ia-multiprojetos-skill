"""Nomes de skill que o preparo do host recusa (1.7.10; MELHORIAS-1.7.10, seção 1, item 8).

No preparo de 26 e 27/10, o `instrucoes_aninhadas.py` sugeriu negar 21 skills do APP Saúde com espaço no nome e o
modelo `{setup-skill-name}` do Site e do Togare, e o `preparo_host.py` recusou todas; o B1 não parou porque o script
saía com código 0. Agora o nome é conferido com a mesma regra do preparo (`NOME_DE_SKILL`, conferida igual pela
leitura do `preparo_host.py`), o que fica fora vai para `nomes_fora_do_padrao` e `neutralizar`, a negação é sugerida
pelo nome da pasta quando ele é válido, e o código de saída é 1. Pasta descartável; nada é executado.

Revisão de segurança da 1.7.10, FLUXB-F3, revisão 2 da correção: o `name` era lido linha a linha, e em formas válidas
de YAML (chave entre aspas, BOM, mapa em linha, nome depois de 64 KiB...) valia o nome da pasta ou outro, enquanto um
leitor de YAML dá o `name` escrito; o `montar` sugeria `--negar-skill <pasta>` e saía calado. Agora o nome só é lido na
forma simples; fora dela, é incerto (fora do padrão, com a pasta a neutralizar), e a pasta entra sempre na negação.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from apoio import SCRIPTS, SKILL, rodar_script

PREPARO = SKILL / "assets" / "host" / "preparo_host.py"
SKILLS = {
    "squad-ok": "squad-ok",
    "agentdb-advanced": "Agentdb Advanced",
    "{setup-skill-name}": "{setup-skill-name}",
    "avaliacao": "Avaliação Clínica",
    "traco": "-começa-com-traço",
    "barra": "a/b",
}


def carregar(nome: str, caminho: Path):
    spec = importlib.util.spec_from_file_location(f"_teste_nomes_{nome}", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class TestNomesDeSkill(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp(prefix="instrucoes-nomes-"))
        self.addCleanup(shutil.rmtree, self.raiz, ignore_errors=True)
        for pasta, nome in SKILLS.items():
            p = self.raiz / "copia" / ".claude" / "skills" / pasta / "SKILL.md"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"---\nname: \"{nome}\"\ndescription: x\n---\n", encoding="utf-8")

    def listar(self) -> tuple[int, dict]:
        p = rodar_script("instrucoes_aninhadas.py", "listar", "--raiz", self.raiz)
        return p.returncode, json.loads(p.stdout)

    def test_regra_igual_a_do_preparo_do_host(self):
        texto = PREPARO.read_text(encoding="utf-8")
        achado = re.search(r'^NOME_DE_SKILL = re\.compile\((r".*")\)$', texto, re.M)
        self.assertIsNotNone(achado, "NOME_DE_SKILL sumiu do preparo_host.py")
        modulo = carregar("instrucoes_aninhadas", SCRIPTS / "instrucoes_aninhadas.py")
        self.assertEqual(modulo.NOME_DE_SKILL.pattern, ast.literal_eval(achado.group(1)))

    def test_nomes_fora_do_padrao_com_motivo_e_negacao_pela_pasta(self):
        codigo, res = self.listar()
        self.assertEqual(codigo, 1, "nome fora do padrão precisa parar o B1")
        fora = {i["nome"]: i for i in res["nomes_fora_do_padrao"]}
        self.assertEqual(sorted(fora), sorted(n for n in SKILLS.values() if n != "squad-ok"))
        self.assertEqual(fora["Agentdb Advanced"]["motivo"], "espaço")
        self.assertEqual(fora["Agentdb Advanced"]["negar_pela_pasta"], "agentdb-advanced")
        self.assertEqual(fora["Agentdb Advanced"]["pasta"], "copia/.claude/skills/agentdb-advanced")
        self.assertEqual(fora["{setup-skill-name}"]["motivo"], "chave")
        self.assertNotIn("negar_pela_pasta", fora["{setup-skill-name}"])  # a pasta também é inválida
        self.assertEqual(fora["Avaliação Clínica"]["motivo"], "espaço, acento")
        self.assertEqual(fora["Avaliação Clínica"]["negar_pela_pasta"], "avaliacao")
        self.assertEqual(fora["-começa-com-traço"]["motivo"], "acento, outro caractere")
        self.assertEqual(fora["a/b"]["motivo"], "outro caractere")
        self.assertEqual(res["sugestoes"]["negar_skills"], ["agentdb-advanced", "avaliacao", "barra", "squad-ok",
                                                            "traco"])
        self.assertEqual(sorted(res["neutralizar"]), sorted(f"copia/.claude/skills/{p}" for p in SKILLS
                                                            if p != "squad-ok"))

    def test_toda_negacao_sugerida_passa_no_preparo_do_host(self):
        _, res = self.listar()
        preparo = carregar("preparo_host", PREPARO)
        perfil = preparo.negar_skills({}, res["sugestoes"]["negar_skills"])
        self.assertEqual(perfil["permissions"]["deny"], res["sugestoes"]["negacoes"])

    def test_motivos(self):
        modulo = carregar("instrucoes_aninhadas_m", SCRIPTS / "instrucoes_aninhadas.py")
        casos = {"ok-1.2_x:y": None, "": "tamanho", "a" * 129: "tamanho", "com espaço": "espaço, acento",
                 "{x}": "chave", "café": "acento", ".oculto": "outro caractere", "x*": "outro caractere",
                 "nome\n": "espaço"}
        for nome, motivo in casos.items():
            with self.subTest(nome=nome):
                self.assertEqual(modulo.motivo_do_nome(nome), motivo)

    def test_todos_validos_sai_com_zero(self):
        shutil.rmtree(self.raiz / "copia")
        p = self.raiz / ".claude" / "skills" / "so-uma" / "SKILL.md"
        p.parent.mkdir(parents=True)
        p.write_text("---\nname: so-uma\n---\n", encoding="utf-8")
        codigo, res = self.listar()
        self.assertEqual((codigo, res["nomes_fora_do_padrao"], res["neutralizar"]), (0, [], []))


# Revisão 2 da correção do FLUXB-F3. Formas válidas de YAML (ou que um leitor de YAML lê de outro jeito) em que um
# leitor dá `name: maliciosa`, e a leitura linha a linha dava o nome da pasta ou outro. As sete primeiras são as da
# revisão (f01 a f04 saíam caladas, com código 0). Uma por pasta: o nome dela é o que o host usaria sem nome.
INCERTAS = {
    "f01": b'---\n"name": maliciosa\n---\n',                                  # chave entre aspas
    "f02": b"\xef\xbb\xbf---\nname: maliciosa\n---\n",                        # BOM antes do '---'
    "f03": b"---\n{name: maliciosa, description: x}\n---\n",                   # mapa em linha
    "f04": b"---\ndescription: " + b"x" * 70_000 + b"\nname: maliciosa\n---\n",  # nome depois de 64 KiB
    "f05": b"---\nname: maliciosa # comentario\n---\n",                         # comentário na linha do nome
    "f06": b"---\nname: >-\n  maliciosa\n---\n",                                # bloco
    "f07": b"---\nname: !!str maliciosa\n---\n",                                # marca
    "f08": b"---\n? name\n: maliciosa\n---\n",                                  # chave explícita
    "f09": b"---\n&a name: maliciosa\n---\n",                                   # âncora na chave
    "f10": b'---\nname: "mal\\x69ciosa"\n---\n',                                # escape entre aspas duplas
    "f11": b"---\nname: mal\n  iciosa\n---\n",                                  # continuação na linha seguinte
    "f12": b"---\nname: legitimo\nname: maliciosa\n---\n",                      # nome repetido
    "f13": b"---\ndescription: x\n<<: {name: maliciosa}\n---\n",                # mescla
    "f14": b"---\n  name: maliciosa\n---\n",                                    # topo recuado
    "f15": b"---\nname: maliciosa\n",                                           # sem o '---' de fecho
    "f16": b"---\nname: legitimo\n...\nname: maliciosa\n---\n",                 # fim de documento no meio
    "f17": b"---\ndescription: a\rname: maliciosa\n---\n",                      # '\r' solto: quebra para o YAML
    "f18": "---\ndescription: a name: maliciosa\n---\n".encode("utf-8"),   # separador de linha Unicode
    "f19": b"   ---\nname: maliciosa\n---\n",                                   # espaço antes do '---'
    # O corte em 64 KiB cai logo depois de '---' numa linha '---x': parece o fecho, mas o leitor segue até o nome.
    "f20": b"---\ndescription: " + b"y" * (65_536 - 21) + b"\n---x\nname: maliciosa\n---\n",
}
# Controles: a forma simples dá o nome escrito; sem frontmatter ou sem `name`, o nome da pasta.
CERTAS = {
    "c01": (b"---\nname: simples\n---\n", "simples"),
    "c02": (b"---\nname: 'entre-aspas'\n---\n", "entre-aspas"),
    "c03": (b'---\nname: "duplas"\ndescription: x\n---\n', "duplas"),
    "c04": (b"---\r\nname: crlf\r\ndescription: x\r\n---\r\nTexto.\r\n", "crlf"),
    "c05": (b"# sem frontmatter\nTexto.\n", "c05"),
    "c06": (b"---\ndescription: sem nome\n---\n", "c06"),
    "c07": (b"---\ndescription: >\n  texto longo\n  em duas linhas\nname: depois-do-bloco\nallowed-tools:\n- Read\n"
            b"- Grep\n---\n", "depois-do-bloco"),
    "c08": (b"---\nname: antes-do-comentario\n# comentario\ndescription: x\n---\n", "antes-do-comentario"),
}


def criar_skills(raiz: Path, conteudos: dict) -> None:
    for pasta, dados in conteudos.items():
        p = raiz / ".claude" / "skills" / pasta / "SKILL.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(dados)


class TestFormaDoFrontmatter(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp(prefix="instrucoes-forma-"))
        self.addCleanup(shutil.rmtree, self.raiz, ignore_errors=True)
        self.mod = carregar("instrucoes_aninhadas_forma", SCRIPTS / "instrucoes_aninhadas.py")

    def test_nome_so_na_forma_simples(self):
        for pasta, dados in INCERTAS.items():
            with self.subTest(pasta):
                self.assertIsNone(self.mod.nome_da_skill(dados[:self.mod.INICIO], pasta))
        for pasta, (dados, nome) in CERTAS.items():
            with self.subTest(pasta):
                self.assertEqual(self.mod.nome_da_skill(dados[:self.mod.INICIO], pasta), nome)

    def test_nome_incerto_vai_para_os_fora_do_padrao_e_a_pasta_para_a_negacao(self):
        criar_skills(self.raiz, {**INCERTAS, **{pasta: dados for pasta, (dados, _n) in CERTAS.items()}})
        p = rodar_script("instrucoes_aninhadas.py", "listar", "--raiz", self.raiz)
        self.assertEqual(p.returncode, 1, "nome incerto precisa parar o B1: " + p.stdout[-500:] + p.stderr)
        res = json.loads(p.stdout)
        fora = {i["pasta"].rpartition("/")[2]: i for i in res["nomes_fora_do_padrao"]}
        self.assertEqual(sorted(fora), sorted(INCERTAS))
        for pasta, item in fora.items():
            with self.subTest(pasta):
                self.assertEqual((item["nome"], item["motivo"], item["negar_pela_pasta"]),
                                 (None, "nome incerto: frontmatter fora da forma simples", pasta))
        self.assertEqual(res["neutralizar"], sorted(f".claude/skills/{p}" for p in INCERTAS))
        esperadas = set(INCERTAS) | set(CERTAS) | {nome for _d, nome in CERTAS.values()}
        self.assertEqual(res["sugestoes"]["negar_skills"], sorted(esperadas))
        self.assertNotIn("maliciosa", res["sugestoes"]["negar_skills"])

    def test_skill_md_nao_lido_tambem_e_nome_incerto(self):
        criar_skills(self.raiz, {"ligada": b"---\nname: maliciosa\n---\n"})
        skill = self.raiz / ".claude" / "skills" / "ligada" / "SKILL.md"
        try:
            os.link(skill, self.raiz / "outro-nome.md")  # vínculo físico: o conteúdo não é lido (R177-VAL-02)
        except OSError as exc:
            self.skipTest(f"vínculo físico indisponível: {exc}")
        res = self.mod.listar(self.raiz.resolve())
        item = res["nomes_fora_do_padrao"][0]
        self.assertEqual((item["nome"], item["motivo"], item["negar_pela_pasta"]),
                         (None, "nome incerto: SKILL.md não lido", "ligada"))
        self.assertEqual(res["sugestoes"]["negar_skills"], ["ligada"])
        self.assertEqual(res["neutralizar"], [".claude/skills/ligada"])


GIT = shutil.which("git")


@unittest.skipUnless(GIT, "git ausente: o montar precisa dele")
class TestMontarComNomeIncerto(unittest.TestCase):
    """Revisão 2 da correção do FLUXB-F3, de ponta a ponta: o repositório com as sete formas da revisão, montado pelo
    `git_projeto.py montar`, sugeria `--negar-skill <pasta>` e não avisava dos nomes fora do padrão."""

    def setUp(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="instrucoes-montar-forma-")))
        git_projeto = carregar("git_projeto_forma", SCRIPTS / "git_projeto.py")
        self.addCleanup(git_projeto.apagar, self.base)
        (self.base / "casa").mkdir()
        (self.base / "gitconfig-vazio").write_bytes(b"")
        self.env = {**os.environ, "HOME": str(self.base / "casa"), "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": str(self.base / "gitconfig-vazio")}
        (self.base / "raiz" / "projects" / "p").mkdir(parents=True)

    def git(self, *args) -> None:
        identidade = ["-c", "user.name=teste", "-c", "user.email=teste@localhost", "-c", "core.autocrlf=false"]
        r = subprocess.run([GIT, *identidade, *map(str, args)], env=self.env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120, cwd=str(self.base))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_montar_avisa_e_nega_pela_pasta(self):
        repo = self.base / "origem"
        self.git("init", "-q", "-b", "main", repo)
        sete = {pasta: INCERTAS[pasta] for pasta in ("f01", "f02", "f03", "f04", "f05", "f06", "f07")}
        criar_skills(repo, sete)
        (repo / "app.py").write_text("print('ok')\n", encoding="utf-8", newline="\n")
        self.git("-C", repo, "add", "-A")
        self.git("-C", repo, "commit", "-qm", "um")
        r = rodar_script("git_projeto.py", "montar", "--raiz", self.base / "raiz", "--projeto", "p", "--de", repo,
                         "--pasta", "repo")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        res = json.loads(r.stdout)
        conf = res["instrucoes_aninhadas"]
        self.assertEqual(conf["negar_skills"], sorted(sete))
        self.assertEqual(sorted(i["pasta"] for i in conf["nomes_fora_do_padrao"]),
                         sorted(f".claude/skills/{p}" for p in sete))
        self.assertTrue(conf["completo"], "a .git da raiz do clone fica sem registro")
        aviso = next(a for a in res["avisos"] if "neutralize estas pastas" in a)
        for pasta in sete:
            self.assertIn(f".claude/skills/{pasta}", aviso)
        self.assertNotIn("maliciosa", " | ".join(res["avisos"]))


if __name__ == "__main__":
    unittest.main()
