"""Skills com scripts de plugin pela ficha de aberturas (1.7.11, lote S1; desenho de skills e agentes, §3.1, §4 e §5).

O item `plugins[].skills_com_scripts[]` da ficha abre o `.py` de `skills/<skill>/scripts/` e o `requirements.lock`, presos
por SHA-256. Cada regra tem a prova negativa dela:
- ficha: modo `caixa` (só com o lote S4), modo desconhecido, caminho fora de `skills/<skill>/scripts/<arquivo>.py`, nome,
  hash e campo a mais ou a menos, repetição, tetos (5 skills por plugin, 10 e 20 scripts na ficha), prefixo `<projeto>-`,
  e `dependencias` (lock de outro lugar, rodas em data/ ou no candidato, Python fora da lista, contagem);
- lock: opção de pip, URL, caminho, marcador, pacote sem hash ou sem versão fixa, repetido, fora do ASCII, grande demais;
- texto do `.py`: `#!`, binário, controle e direção, CR sozinho, BOM fora do começo, codificação que não é utf-8;
- disco: `.py` ou lock sem item na ficha, script a mais ou a menos, hash trocado na ficha ou no arquivo depois da
  assinatura, `.py` fora do lugar mesmo listado, outras linguagens, bit de execução e o conteúdo no DrvFs sem metadata.
Só dados fictícios, em pastas temporárias; nada do plugin é executado.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from helpers import KIT  # noqa: F401 (o kit no sys.path)

from fundacao.core import aberturas_markdown as markdown
from fundacao.core import aberturas_plugins as plugins
from fundacao.core import aberturas_regras as regras
from fundacao.core import aberturas_scripts as scripts

HOJE, PROJETO, SKILL = date(2026, 11, 8), "juridico-lab", "scrapjur"
PLUGIN = f"{PROJETO}-{SKILL}"
CAMINHO = f"skills/{SKILL}/scripts/buscar.py"
RODAS = "outputs/rodas-scrapjur-20261108"
SCRIPT = "import json\nprint(json.dumps({'ok': True}))\n"
SKILL_MD = f"---\nname: {SKILL}\ndescription: Busca (fictícia).\n---\n\nUse o executor.\n"
H = lambda c: f" \\\n    --hash=sha256:{c * 64}"  # noqa: E731 (uma linha de hash do lock)
LOCK = f"# rodas: {RODAS}\nalfa==1.0{H('a')}{H('b')}\nBeta_Pacote[extra]==2.1.post1{H('c')}\n"


PADRAO = object()


def script(nome="buscar", sha="a" * 64, modo="sessao", caminho=PADRAO) -> dict:
    return {"nome": nome, "caminho": f"skills/{SKILL}/scripts/{nome.replace('-', '_')}.py" if caminho is PADRAO
            else caminho, "sha256": sha, "modo": modo}


def deps(**mud) -> dict:
    return {"lock": f"skills/{SKILL}/requirements.lock", "lock_sha256": "d" * 64, "rodas": RODAS, "python": "3.12",
            "pacotes": 2, **mud}


def skill(**mud) -> dict:
    return {"skill": SKILL, "skill_md_sha256": "e" * 64, "scripts": [script()], "dependencias": deps(), **mud}


def plugin(skills=None, nome=PLUGIN) -> dict:
    return {"nome": nome, "origem": f"plugins-candidatos/{nome}", "manifesto_sha256": "b" * 64,
            "skills_com_scripts": [skill()] if skills is None else skills}


def ficha(*plugins_) -> dict:
    return {"schema_version": regras.SCHEMA, "ficha_id": "aberturas-juridico-lab", "project_id": PROJETO, "versao": 1,
            "motivo": "Liberar o script de busca da skill.", "consequencias": "A sessão poderá rodar o script.",
            "plugins": list(plugins_)}


def campos(f) -> list[str]:
    return [e["campo"] for e in regras.validar(f, projeto=PROJETO, hoje=HOJE)["erros"]]


class FichaDosScripts(unittest.TestCase):
    def test_skill_conforme_vale_e_aparece_em_itens_e_na_tela(self):
        f = ficha(plugin())
        self.assertEqual(regras.validar(f, projeto=PROJETO, hoje=HOJE), {"erros": [], "avisos": []})
        self.assertEqual([i for s, i in regras.itens(f) if s == "scripts"], [f"{PLUGIN}:{SKILL}/buscar (SHA-256 {'a' * 12})"])
        self.assertEqual([i for s, i in regras.itens(f) if s == "dependencias"],
                         [f"{PLUGIN}:{SKILL} (2 pacotes, lock SHA-256 {'d' * 12})"])
        tela = {d["secao"]: d["texto"] for d in regras.descrever(f)}
        self.assertIn("é um PROGRAMA", tela["scripts"])
        self.assertIn("mesma autoridade dos comandos da sessão", tela["scripts"])
        self.assertIn("não o que ele faz", tela["scripts"])
        self.assertIn("usa 2 pacotes de terceiros", tela["dependencias"])
        self.assertIn("não que são seguros", tela["dependencias"])
        self.assertIn("scripts Python listados abaixo", tela["plugins"])
        self.assertNotIn("sem hooks, MCP nem executável", tela["plugins"])

    def test_sem_o_campo_ou_com_a_lista_vazia_nada_abre_e_o_plugin_de_markdown_segue_com_aviso(self):
        for p in ({k: v for k, v in plugin().items() if k != "skills_com_scripts"} | {"nome": "outro"},
                  plugin([], nome="outro")):
            with self.subTest(campo="skills_com_scripts" in p):
                f = ficha(dict(p, origem="plugins-candidatos/outro"))
                resultado = regras.validar(f, projeto=PROJETO, hoje=HOJE)
                self.assertEqual(resultado["erros"], [])
                self.assertTrue([a for a in resultado["avisos"] if "prefixo do projeto" in a["motivo"]])
                self.assertEqual([s for s, _ in regras.itens(f) if s in ("scripts", "dependencias")], [])
        self.assertIn("sem hooks, MCP nem executável", regras.descrever(ficha(plugin([], PLUGIN)))[0]["texto"])

    def test_plugin_com_scripts_sem_o_prefixo_do_projeto_e_erro(self):
        achados = regras.validar(ficha(plugin(nome="scrapjur")), projeto=PROJETO, hoje=HOJE)
        self.assertEqual([e["campo"] for e in achados["erros"]], ["plugins[0].nome"])
        self.assertIn(f"{PROJETO}-<nome>", achados["erros"][0]["motivo"])

    def test_modo_caixa_so_com_o_lote_s4_e_modo_desconhecido_recusa(self):
        alvo = "plugins[0].skills_com_scripts[0].scripts[0].modo"
        achados = regras.validar(ficha(plugin([skill(scripts=[script(modo="caixa")])])), projeto=PROJETO, hoje=HOJE)
        self.assertEqual([e["campo"] for e in achados["erros"]], [alvo])
        self.assertEqual(achados["erros"][0]["versao"], "1.7.11")
        self.assertIn("lote S4", achados["erros"][0]["motivo"])
        for modo in ("jaula", "Sessao", "", None, 1):
            self.assertEqual(campos(ficha(plugin([skill(scripts=[script(modo=modo)])]))), [alvo])
        with mock.patch.object(scripts, "MODOS_ABERTOS", ("sessao", "caixa")):  # o S4 abre a caixa
            self.assertEqual(campos(ficha(plugin([skill(scripts=[script(modo="caixa")])]))), [])

    def test_caminho_fora_de_skills_skill_scripts_arquivo_py_recusa(self):
        ruins = ("skills/scrapjur/buscar.py", "skills/scrapjur/scripts/sub/buscar.py", "skills/outra/scripts/buscar.py",
                 "skills/scrapjur/scripts/Buscar.py", "skills/scrapjur/scripts/__init__.py",
                 "skills/scrapjur/scripts/buscar.sh", "skills/scrapjur/scripts/buscar.PY", "scripts/buscar.py",
                 "skills/scrapjur/scripts/../buscar.py", "skills/scrapjur/scripts/buscar.py/", "/skills/x.py", "", None, 5)
        for caminho in ruins:
            with self.subTest(caminho=caminho):
                f = ficha(plugin([skill(scripts=[script(caminho=caminho)])]))
                self.assertEqual(campos(f), ["plugins[0].skills_com_scripts[0].scripts[0].caminho"])

    def test_nome_hash_campo_e_repeticao_do_script(self):
        base = "plugins[0].skills_com_scripts[0].scripts"
        for nome in ("Buscar", "1x", "x" * 33, "", None, "a_b"):
            self.assertEqual(campos(ficha(plugin([skill(scripts=[script() | {"nome": nome}])]))),
                             [base + "[0].nome"], nome)
        for sha in ("A" * 64, "a" * 63, "", None):
            self.assertEqual(campos(ficha(plugin([skill(scripts=[script(sha=sha)])]))), [base + "[0].sha256"], sha)
        for ruim in (dict(script(), extra=1), {k: v for k, v in script().items() if k != "modo"}, "x", None):
            self.assertEqual(campos(ficha(plugin([skill(scripts=[ruim])]))), [base + "[0]"], str(ruim))
        repetido = [script(), script(sha="c" * 64)]
        self.assertEqual(campos(ficha(plugin([skill(scripts=repetido)]))), [base + "[1].nome", base + "[1].caminho"])
        duas = [script(), script("coletar")]
        self.assertEqual(campos(ficha(plugin([skill(scripts=duas)]))), [])

    def test_nome_do_script_e_o_do_arquivo_sem_py_com_hifen_no_lugar_do_sublinhado(self):
        alvo = "plugins[0].skills_com_scripts[0].scripts[0].nome"
        ok = script("buscar-tudo", caminho=f"skills/{SKILL}/scripts/buscar_tudo.py")
        self.assertEqual(campos(ficha(plugin([skill(scripts=[ok])]))), [])
        for nome, arquivo in (("deletar", "buscar"), ("buscar", "buscar_tudo"), ("buscar_tudo", "buscar_tudo"),
                              ("buscar-tudo", "coletar")):
            with self.subTest(nome=nome, arquivo=arquivo):
                ruim = script(nome, caminho=f"skills/{SKILL}/scripts/{arquivo}.py")
                self.assertIn(alvo, campos(ficha(plugin([skill(scripts=[ruim])]))))
        self.assertTrue(any("o que o titular vê é o que roda" in e["motivo"] for e in regras.validar(ficha(plugin([skill(
            scripts=[script("deletar", caminho=CAMINHO)])])), projeto=PROJETO, hoje=HOJE)["erros"]))

    def test_forma_e_tetos_da_skill(self):
        base = "plugins[0].skills_com_scripts"
        for ruim in (dict(skill(), extra=1), {k: v for k, v in skill().items() if k != "scripts"}, "x", None):
            self.assertEqual(campos(ficha(plugin([ruim]))), [base + "[0]"])
        for nome in ("Scrapjur", "a_b", "-x", "", None):
            self.assertIn(base + "[0].skill", campos(ficha(plugin([skill(skill=nome)]))))
        self.assertEqual(campos(ficha(plugin([skill(), skill()]))), [base + "[1].skill"])
        for scripts_ in ([], "x", None, [script(f"s{i}") for i in range(11)]):
            self.assertEqual(campos(ficha(plugin([skill(scripts=scripts_)]))), [base + "[0].scripts"])
        for sha in ("E" * 64, None):
            self.assertEqual(campos(ficha(plugin([skill(skill_md_sha256=sha)]))), [base + "[0].skill_md_sha256"])
        sem = {k: v for k, v in skill().items() if k != "dependencias"}
        self.assertEqual(campos(ficha(plugin([sem]))), [])  # sem pacotes: só a biblioteca padrão
        cinco = [dict(skill(skill=f"s{i}"), dependencias=deps(lock=f"skills/s{i}/requirements.lock"),
                      scripts=[script(caminho=f"skills/s{i}/scripts/buscar.py")]) for i in range(5)]
        self.assertEqual(campos(ficha(plugin(cinco))), [])
        self.assertEqual(campos(ficha(plugin(cinco + [skill(skill="s5")]))), [base])
        dois = [plugin(cinco, nome=f"{PROJETO}-a"), plugin(cinco, nome=f"{PROJETO}-b")]
        self.assertEqual(campos(ficha(*dois)), [])  # 10 skills na ficha
        mais = [plugin(cinco, nome=f"{PROJETO}-{c}") for c in "abc"]
        self.assertEqual(campos(ficha(*mais)), ["plugins"])  # 15

    def test_vinte_scripts_na_ficha_no_maximo(self):
        def com(n):
            return plugin([skill(skill=f"s{i}", dependencias=deps(lock=f"skills/s{i}/requirements.lock"),
                                 scripts=[script(f"x{j}", caminho=f"skills/s{i}/scripts/x{j}.py") for j in range(n)])
                           for i in range(2)])
        self.assertEqual(campos(ficha(com(10))), [])  # 20
        um = skill(skill="t", scripts=[script(caminho="skills/t/scripts/buscar.py")],
                   dependencias=deps(lock="skills/t/requirements.lock"))
        self.assertEqual(campos(ficha(com(10), plugin([um], nome=f"{PROJETO}-t"))), ["plugins"])  # 21

    def test_dependencias(self):
        base = "plugins[0].skills_com_scripts[0].dependencias"
        casos = {"lock": ("skills/outra/requirements.lock", "skills/scrapjur/sub/requirements.lock", "requirements.lock",
                          None),
                 "lock_sha256": ("D" * 64, "", None),
                 "rodas": ("data/rodas", "plugins-candidatos/rodas", "../rodas", "/tmp/rodas", "C:/rodas", "", None, 3),
                 "python": ("3.11", "3", "3.12.1", None),
                 "pacotes": (0, 301, -1, "2", True, 2.5, None)}
        for campo, valores in casos.items():
            for valor in valores:
                with self.subTest(campo=campo, valor=valor):
                    self.assertEqual(campos(ficha(plugin([skill(dependencias=deps(**{campo: valor}))]))),
                                     [f"{base}.{campo}"])
        for ruim in (dict(deps(), extra=1), {k: v for k, v in deps().items() if k != "rodas"}, "x", [], None):
            self.assertEqual(campos(ficha(plugin([skill(dependencias=ruim)]))), [base], str(ruim))

    def test_ficha_adulterada_nao_derruba_itens_nem_descrever(self):
        for ruim in ({"plugins": [plugin("x")]}, {"plugins": [plugin([5, None, {"skill": 1}])]},
                     {"plugins": [plugin([skill(scripts="x", dependencias=3)])]},
                     {"plugins": [plugin([skill(scripts=[None, 5, {"nome": 1}])])]}, {"plugins": "x"}, {"plugins": [5]}):
            with self.subTest(ruim=str(ruim)[:50]):
                regras.itens(ruim)
                regras.descrever(ruim)
                regras.validar(dict(ficha(), **ruim), projeto=PROJETO, hoje=HOJE)


class LockDosPacotes(unittest.TestCase):
    def motivos(self, texto) -> list[str]:
        return scripts.ler_lock(texto.encode("utf-8") if isinstance(texto, str) else texto)[0]

    def test_lock_conforme_devolve_os_nomes_normalizados(self):
        self.assertEqual(scripts.ler_lock(LOCK.encode()), ([], ["alfa", "beta-pacote"]))
        self.assertEqual(scripts.ler_lock(LOCK.replace("\n", "\r\n").encode())[0], [])

    def test_o_que_o_lock_nao_aceita(self):
        casos = {"-e .": "opção de pip", "-r outro.txt": "opção de pip", "--index-url https://x.example/simple": "opção",
                 f"--extra-index-url https://x.example{H('a')}": "opção", f"alfa @ https://x.example/a.whl{H('a')}": "URL",
                 f"alfa==1.0{H('a')}\n": None, "alfa==1.0 --hash=sha256:" + "a" * 64: "linha fora da forma",
                 "alfa==1.0": "sem --hash", "alfa": "sem versão fixa", f"alfa>=1.0{H('a')}": "sem versão fixa",
                 f"alfa==1.0{H('A')}": "linha fora da forma", "alfa==1.0 \\\n    --hash=md5:" + "a" * 32: "sem --hash",
                 f"alfa==1.0; python_version < '3.12'{H('a')}": "marcador", f"./alfa.whl{H('a')}": "caminho",
                 f"../alfa==1.0{H('a')}": "caminho", f"alfa==1.0{H('a')}\nalfa==1.0{H('b')}": "pacote repetido",
                 f"Alfa==1.0{H('a')}\nalfa==1.0{H('b')}": "pacote repetido",
                 f"alfa_b==1.0{H('a')}\nalfa-b==1.0{H('b')}": "pacote repetido",
                 f"alfa==1.0{H('a')}\n# comentario no meio\n    --hash=sha256:{'b' * 64}": "opção de pip",
                 f"alfa==1.0 \\\n# comentario na continuacao{H('a')}": "linha fora", "# so comentario\n": "lock sem pacote",
                 "": "lock sem pacote", f"alfa==1.0{H('a')}\ttab": "controle", "# acentuação: ção\n": "ASCII",
                 f"alfa==1.0{H('a')}\r": "controle"}
        for texto, trecho in casos.items():
            if trecho is None:
                self.assertEqual(self.motivos(texto), [], texto)
                continue
            with self.subTest(texto=texto[:50]):
                achados = self.motivos(texto)
                self.assertTrue(achados and trecho in " | ".join(achados), (texto, achados))

    def test_tetos_do_lock(self):
        pacotes = "".join(f"p{i}==1.0{H('a')}\n" for i in range(300))
        self.assertEqual(scripts.ler_lock(pacotes.encode())[0], [])
        self.assertIn("mais de 300", " ".join(self.motivos(pacotes + f"p300==1.0{H('a')}\n")))
        self.assertIn("acima de 65536", " ".join(self.motivos("# x\n" * 17000)))
        muitos = "".join(f"opcao-{i}\n" for i in range(20))
        self.assertLessEqual(len(self.motivos(muitos)), 9)  # os primeiros e o resumo


class TextoDoPython(unittest.TestCase):
    def achados(self, dados) -> list[str]:
        saida = []
        markdown.conferir_python("skills/s/scripts/a.py", dados if isinstance(dados, bytes) else dados.encode("utf-8"),
                                 lambda rel, motivo, versao=None: saida.append(motivo))
        return saida

    def test_python_conforme(self):
        for texto in (SCRIPT, "\ufeff" + SCRIPT, SCRIPT.replace("\n", "\r\n"), "# coding: utf-8\n" + SCRIPT,
                      "# -*- coding: UTF_8 -*-\n" + SCRIPT, "# vim: set fileencoding=utf8 :\n" + SCRIPT, "ação = 1\n"):
            self.assertEqual(self.achados(texto), [], texto[:30])

    def test_o_que_o_texto_do_python_nao_aceita(self):
        casos = {"#!/usr/bin/env python3\n" + SCRIPT: "tire a primeira linha #!", b"\x7fELF\x02\x01": "ELF ou MZ",
                 b"MZ texto\n": "ELF ou MZ", b"\xff\xfe=": "fora do UTF-8", "x = 1\x00\n": "controle",
                 f"x = '{chr(0x202e)}'\n": "controle", "x = 1\ry = 2\n": "CR sozinho", f"x = 1{chr(0x2028)}y = 2\n": "U+2028",
                 SCRIPT + "\ufeff": "U+FEFF", "# coding: latin-1\n" + SCRIPT: "só utf-8", "\n# coding=utf-7\n": "só utf-8",
                 "# coding: cp1252\n": "só utf-8", "x = 1\n" * (markdown.TETO_PY // 6 + 1): "acima de"}
        for dados, trecho in casos.items():
            with self.subTest(dados=str(dados)[:40]):
                self.assertTrue(any(trecho in m for m in self.achados(dados)), (dados, self.achados(dados)))
        self.assertEqual(self.achados("a = 1\nb = 2\n# coding: latin-1\n"), [])  # só as duas primeiras linhas valem


class NoDisco(unittest.TestCase):
    """O plugin no disco contra o item da ficha."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="aberturas-scripts-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.pasta = self.base / "plugins-candidatos" / PLUGIN
        self.montar()

    def montar(self, extras: dict | None = None) -> None:
        shutil.rmtree(self.pasta, ignore_errors=True)
        padrao = {".claude-plugin/plugin.json": json.dumps({"name": PLUGIN, "description": "Plugin fictício."}),
                  f"skills/{SKILL}/SKILL.md": SKILL_MD, f"skills/{SKILL}/scripts/buscar.py": SCRIPT,
                  f"skills/{SKILL}/requirements.lock": LOCK, "LICENSE": "Licença fictícia.\n"}
        for rel, texto in {**padrao, **(extras or {})}.items():
            if texto is None:
                continue
            alvo = self.pasta.joinpath(*rel.split("/"))
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_bytes(texto if isinstance(texto, bytes) else texto.encode("utf-8"))

    def sha(self, rel: str) -> str:
        return hashlib.sha256(self.pasta.joinpath(*rel.split("/")).read_bytes()).hexdigest()

    def lista(self, **mud) -> list[dict]:
        return [{"skill": SKILL, "skill_md_sha256": self.sha(f"skills/{SKILL}/SKILL.md"),
                 "scripts": [script(sha=self.sha(CAMINHO))],
                 "dependencias": deps(lock_sha256=self.sha(f"skills/{SKILL}/requirements.lock")), **mud}]

    def item(self, lista=None) -> dict:
        lista = self.lista() if lista is None else lista
        res = plugins.conferir_pasta_do_plugin(self.pasta, PLUGIN, lista)
        self.assertEqual(res["erros"], [])
        return {"nome": PLUGIN, "origem": f"plugins-candidatos/{PLUGIN}", "manifesto_sha256": res["manifesto_sha256"],
                "skills_com_scripts": lista}

    def motivos(self, item: dict) -> str:
        return " | ".join(f"{e['campo']}: {e['motivo']}" for e in plugins.conferir_plugin(self.base, item)["erros"])

    def test_script_e_lock_listados_valem_e_o_manifesto_leva_os_dois(self):
        item = self.item()
        res = plugins.conferir_plugin(self.base, item)
        self.assertEqual((res["erros"], res["manifesto_sha256"]), ([], item["manifesto_sha256"]))
        caminhos = {a["caminho"] for a in res["arquivos"]}
        self.assertLessEqual({CAMINHO, f"skills/{SKILL}/requirements.lock"}, caminhos)
        sem_lock = self.lista()
        del sem_lock[0]["dependencias"]
        self.assertIn("só Markdown", self.motivos(dict(item, skills_com_scripts=sem_lock)))  # o lock sem item recusa

    def test_py_e_lock_sem_item_na_ficha_recusam_o_plugin_inteiro(self):
        for skills in (None, []):
            with self.subTest(skills=skills):
                res = plugins.conferir_pasta_do_plugin(self.pasta, PLUGIN, skills)
                self.assertIsNone(res["manifesto_sha256"])
                self.assertIn(CAMINHO, " ".join(e["campo"] for e in res["erros"]))
                self.assertTrue(any("script sem item em skills_com_scripts" in e["motivo"] and e.get("versao") == "1.7.11"
                                    for e in res["erros"]), res["erros"])
        item = {k: v for k, v in self.item().items() if k != "skills_com_scripts"}
        self.assertIn("script sem item", self.motivos(item))

    def test_script_a_mais_ou_a_menos_na_ficha_recusa(self):
        self.montar({f"skills/{SKILL}/scripts/extra.py": SCRIPT})
        self.assertIn("script sem item", self.motivos(self.item_sem_conferir()))
        self.montar()
        faltando = self.lista(scripts=[script(sha=self.sha(CAMINHO)), script("fantasma", "f" * 64)])
        self.assertIn("não está no plugin em skills/<skill>/scripts/<arquivo>.py", self.motivos(self.item_sem_conferir(faltando)))
        outra = self.lista(skill="outra")
        self.assertIn("não tem skills/<skill>/SKILL.md", self.motivos(self.item_sem_conferir(outra)))

    def item_sem_conferir(self, lista=None) -> dict:
        lista = self.lista() if lista is None else lista
        res = plugins.conferir_pasta_do_plugin(self.pasta, PLUGIN)  # o manifesto sem a lista (pode ter erro)
        manifesto = res["manifesto_sha256"] or plugins.sha256_do_manifesto(
            [dict(caminho=r.relative_to(self.pasta).as_posix(), bytes=r.stat().st_size, sha256=hashlib.sha256(
                r.read_bytes()).hexdigest()) for r in sorted(self.pasta.rglob("*")) if r.is_file()])
        return {"nome": PLUGIN, "origem": f"plugins-candidatos/{PLUGIN}", "manifesto_sha256": manifesto,
                "skills_com_scripts": lista}

    def test_hash_trocado_na_ficha_ou_no_arquivo_depois_da_assinatura_recusa(self):
        item = self.item()
        casos = {"scripts": [script(sha="9" * 64)], "skill_md_sha256": "9" * 64,
                 "dependencias": deps(lock_sha256="9" * 64)}
        textos = {"scripts": "SHA-256 do script difere de scripts[].sha256", "skill_md_sha256": "SKILL.md difere",
                  "dependencias": "SHA-256 do lock difere de dependencias.lock_sha256"}
        for campo, valor in casos.items():  # N-HASH-5: o manifesto está certo, o hash da ficha não
            with self.subTest(campo=campo):
                self.assertIn(textos[campo], self.motivos(dict(item, skills_com_scripts=self.lista(**{campo: valor}))))
        for rel, novo in ((CAMINHO, SCRIPT + "print('outro')\n"), (f"skills/{SKILL}/SKILL.md", SKILL_MD + "Mais.\n"),
                          (f"skills/{SKILL}/requirements.lock", LOCK + "gama==1.0" + H("d") + "\n")):
            with self.subTest(arquivo=rel):  # N-HASH-1: o arquivo muda depois da assinatura
                self.montar()
                item = self.item()
                (self.pasta.joinpath(*rel.split("/"))).write_text(novo, encoding="utf-8")
                self.assertIn("o plugin mudou desde o manifesto da ficha", self.motivos(item))
                self.assertIn("difere", self.motivos(dict(item, manifesto_sha256="")))  # sem o manifesto, o hash da ficha

    def test_lock_com_contagem_errada_ou_fora_da_forma_recusa(self):
        item = self.item()
        self.assertIn("o lock tem 2 pacotes e a ficha diz 3", self.motivos(dict(item, skills_com_scripts=self.lista(
            dependencias=deps(lock_sha256=self.sha(f"skills/{SKILL}/requirements.lock"), pacotes=3)))))
        for texto, trecho in (("-e .\n", "opção de pip"), (f"alfa==1.0\n", "sem --hash"),
                              (f"alfa @ https://x.example/a.whl{H('a')}\n", "URL")):
            with self.subTest(texto=texto):
                self.montar({f"skills/{SKILL}/requirements.lock": f"# rodas: {RODAS}\n" + texto})
                self.assertIn(trecho, self.motivos(self.item_sem_conferir()))

    def test_py_e_lock_fora_do_lugar_recusam_mesmo_listados(self):
        for rel in ("skills/scrapjur/buscar.py", "skills/scrapjur/scripts/sub/buscar.py", "agents/buscar.py",
                    "commands/buscar.py", "skills/scrapjur/scripts/Coletar.py", "skills/scrapjur/scripts/__init__.py",
                    "skills/scrapjur/scripts/coletar.PY", "skills/Outra/scripts/buscar.py",
                    "skills/scrapjur/sub/requirements.lock", "agents/requirements.lock"):
            with self.subTest(rel=rel):
                self.montar({rel: SCRIPT if rel.lower().endswith(".py") else LOCK})
                lista = self.lista(scripts=[script(sha=self.sha(CAMINHO)), script("fora", caminho=rel, sha=self.sha(rel))])
                res = plugins.conferir_plugin(self.base, self.item_sem_conferir(lista))
                self.assertTrue(res["erros"], rel)
                self.assertIsNone(res["manifesto_sha256"])

    def test_outras_linguagens_recusam_mesmo_listadas(self):
        for nome in ("buscar.sh", "buscar.js", "buscar.pyc", "buscar.ps1", "buscar.so", "buscar.exe", "buscar.pyw", "buscar.bat"):
            with self.subTest(nome=nome):
                rel = f"skills/{SKILL}/scripts/{nome}"
                self.montar({rel: "echo ficticio\n"})
                lista = self.lista(scripts=[script(sha=self.sha(CAMINHO)), script("outro", caminho=rel, sha=self.sha(rel))])
                self.assertIn("executável ou script no plugin: só na 1.7.11", self.motivos(self.item_sem_conferir(lista)))

    def test_texto_do_py_recusa_dentro_do_plugin(self):
        casos = {"#!/usr/bin/env python3\n" + SCRIPT: "tire a primeira linha #!", f"x = '{chr(0x202e)}'\n": "controle",
                 "# coding: latin-1\n" + SCRIPT: "só utf-8", b"\xff\xfe": "fora do UTF-8", b"\x7fELF\x02": "ELF ou MZ",
                 "x = 1\n" * 90000: "acima de"}
        for texto, trecho in casos.items():
            with self.subTest(texto=str(texto)[:30]):
                self.montar({CAMINHO: texto})
                self.assertIn(trecho, self.motivos(self.item_sem_conferir()))

    @unittest.skipUnless(os.name == "posix", "bit de execução só existe fora do Windows")
    def test_bit_de_execucao_e_o_conteudo_no_drvfs_sem_metadata(self):
        item = self.item()
        os.chmod(self.pasta / CAMINHO, 0o755)
        self.assertIn("bit de execução", self.motivos(item))
        os.chmod(self.pasta / CAMINHO, 0o644)
        self.assertEqual(plugins.conferir_plugin(self.base, item)["erros"], [])
        with mock.patch.object(plugins, "bit_de_execucao_vale", return_value=False):  # DrvFs: todo arquivo é 0777
            os.chmod(self.pasta / CAMINHO, 0o777)
            self.assertEqual(plugins.conferir_plugin(self.base, item)["erros"], [])
            self.montar({CAMINHO: "#!/bin/sh\n"})
            self.assertIn("executável ou script no plugin pelo conteúdo", self.motivos(self.item_sem_conferir()))

    def test_ligacao_no_lugar_do_script_recusa(self):
        item = self.item()
        alvo = self.base / "fora.py"
        alvo.write_text(SCRIPT, encoding="utf-8")
        (self.pasta / CAMINHO).unlink()
        try:
            os.symlink(alvo, self.pasta / CAMINHO)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"link simbólico indisponível: {exc}")
        self.assertIn("ligação", self.motivos(item))

    def test_itens_mostram_o_script_trocado_como_o_que_fecha_e_o_que_abre(self):
        antes = regras.itens(ficha(plugin([skill(scripts=[script(sha="a" * 64)])])))
        depois = regras.itens(ficha(plugin([skill(scripts=[script(sha="f" * 64)])])))
        self.assertEqual(len(set(antes) ^ set(depois)), 2)


if __name__ == "__main__":
    unittest.main()
