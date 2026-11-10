"""Plugin `codigo-enxuto` entregue pela skill (1.7.11; ponytail, P2): só Markdown, na forma de hoje do plugin candidato.

No pacote, as skills do plugin se chamam `SKILL.modelo.md` (o pacote tem um único `SKILL.md`); o
`plugin_codigo_enxuto.py montar` as leva a um projeto com o nome `SKILL.md`, pelo `montar` do `plugin_candidato.py`, e o
candidato montado passa no `conferir` e leva os dois avisos de licença. A prova negativa mostra que a forma não se abriu: hooks de plugin, `plugin.json`
com `hooks` e `userConfig`, mods, arquivos `.js` e `.mcp.json` continuam recusados, cada um com o motivo e a marca
"1.7.11" que o código ainda traz; e o `montar` de uma árvore no formato do ponytail (fictícia, sem código dele) deixa
`hooks/` e `scripts/` em `nao_copiados`. Pastas descartáveis; nada do candidato é executado.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from unittest import mock

from apoio import SCRIPTS, SKILL, criar_ligacao_dir
from test_plugin_candidato import MOD, Fundacao, ambiente_sem_sessao, escrever
from test_avisos_de_terceiros import TEXTO_MIT

_spec = importlib.util.spec_from_file_location('plugin_codigo_enxuto_teste', SCRIPTS / 'plugin_codigo_enxuto.py')
MONTAR = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(MONTAR)
PLUGIN = SKILL / "assets" / "plugins" / "codigo-enxuto"
SKILLS = ("enxuto", "enxuto-auditoria", "enxuto-dividas", "enxuto-revisao")
ARQUIVOS = [".claude-plugin/plugin.json", "LICENSE", *(f"skills/{n}/SKILL.modelo.md" for n in SKILLS)]
HOOK_DE_PLUGIN = json.dumps({"hooks": {"SessionStart": [{"matcher": "startup|resume|clear|compact", "hooks": [
    {"type": "command", "command": "node ${CLAUDE_PLUGIN_ROOT}/hooks/ativar.js"}]}]}})


def copiar_sem_o_modo(origem: Path, destino: Path) -> None:
    """Copia a árvore só pelo conteúdo, com o modo padrão do sistema: na árvore da skill em /mnt/<letra> (DrvFs sem
    metadata) todo arquivo aparece 0777, e a cópia com o modo da origem levaria o bit de execução, que a conferência do
    Ubuntu recusa."""
    for arquivo in sorted(origem.rglob("*")):
        alvo = destino / arquivo.relative_to(origem)
        if arquivo.is_dir():
            alvo.mkdir(parents=True, exist_ok=True)
        else:
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_bytes(arquivo.read_bytes())


def arquivos_de(pasta: Path) -> list:
    return sorted(p.relative_to(pasta).as_posix() for p in pasta.rglob("*") if p.is_file())


class PluginEntregue(Fundacao, unittest.TestCase):
    def test_so_os_arquivos_previstos_e_nenhum_se_chama_skill_md(self):
        self.assertEqual(arquivos_de(PLUGIN), sorted(ARQUIVOS))
        # CEN-11, "um único SKILL.md no pacote": o do plugin só existe depois da montagem, dentro de um projeto
        self.assertEqual([p for p in SKILL.rglob("SKILL.md") if p != SKILL / "SKILL.md"], [])
        self.assertFalse(MOD.conferir(PLUGIN)["conforme"], "como está no pacote, ainda não é um plugin (sem SKILL.md)")

    def test_o_candidato_montado_passa_no_conferir_e_tem_o_manifesto_do_montar(self):
        res = MONTAR.montar(self.raiz, "demo")
        candidato = Path(res["candidato"])
        conferido = MOD.conferir(candidato)
        self.assertTrue(conferido["conforme"], conferido["motivos"])
        self.assertEqual((conferido["nome"], conferido["avisos"], conferido["arquivos"]),
                         ("demo-codigo-enxuto", [], len(ARQUIVOS)))
        self.assertEqual({c["invocacao"] for c in conferido["componentes"]}, {f"/demo-codigo-enxuto:{n}" for n in SKILLS})
        self.assertEqual((conferido["manifesto"], conferido["manifesto_sha256"]), MOD.manifesto(candidato))
        self.assertEqual(res["manifesto_sha256"], conferido["manifesto_sha256"])
        self.assertEqual(arquivos_de(candidato), sorted([".claude-plugin/plugin.json", "LICENSE",
                                                         *(f"skills/{n}/SKILL.md" for n in SKILLS)]))
        for n in SKILLS:  # o conteúdo é o do modelo, byte a byte
            self.assertEqual((candidato / "skills" / n / "SKILL.md").read_bytes(),
                             (PLUGIN / "skills" / n / "SKILL.modelo.md").read_bytes())

    def test_montar_pela_linha_de_comando_e_conferir_dao_zero(self):
        r = subprocess.run([sys.executable, "-B", str(SCRIPTS / "plugin_codigo_enxuto.py"), "montar", "--raiz",
                            str(self.raiz), "--projeto", "demo"], capture_output=True, text=True, encoding="utf-8",
                           env=ambiente_sem_sessao(), timeout=180)
        self.assertEqual(r.returncode, 0, r.stdout[-600:] + r.stderr[-300:])
        res = json.loads(r.stdout)
        self.assertEqual((res["feito"], res["nome"], res["nao_copiados"], res["avisos"]),
                         ("montar-codigo-enxuto", "demo-codigo-enxuto", [], []))
        c = subprocess.run([sys.executable, "-B", str(SCRIPTS / "plugin_candidato.py"), "conferir", "--pasta",
                            res["candidato"]], capture_output=True, text=True, encoding="utf-8",
                           env=ambiente_sem_sessao(), timeout=180)
        self.assertEqual(c.returncode, 0, c.stdout[-600:] + c.stderr[-300:])
        self.assertTrue(json.loads(c.stdout)["conforme"])

    def test_plugin_json_so_com_as_chaves_da_forma(self):
        dados = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(dados["name"], "codigo-enxuto")
        self.assertLessEqual(set(dados), {"name", "version", "description"})

    def test_licenca_leva_os_dois_avisos(self):
        texto = (PLUGIN / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("Copyright (c) 2026 opera02", texto)
        self.assertIn("Copyright (c) 2026 DietrichGebert", texto)
        self.assertEqual(texto.count(TEXTO_MIT), 2)
        self.assertEqual(texto.count("The above copyright notice and this permission notice shall be included"), 2)
        self.assertIn("github.com/DietrichGebert/ponytail", texto)
        self.assertIn("96608e0", texto)
        self.assertNotIn(b"\r", (PLUGIN / "LICENSE").read_bytes())
        # a licença da skill (LICENSE.txt) é a primeira parte, sem alteração
        propria = (SKILL / "LICENSE.txt").read_text(encoding="utf-8").strip()
        self.assertIn(propria, texto)

    def test_cada_skill_tem_nome_da_pasta_formato_e_so_o_nivel_padrao(self):
        for nome in SKILLS:
            with self.subTest(skill=nome):
                texto = (PLUGIN / "skills" / nome / "SKILL.modelo.md").read_text(encoding="utf-8")
                cabeca, corpo = texto.split("---\n", 2)[1:]
                self.assertIn(f"name: {nome}\n", cabeca)
                self.assertIn("license: MIT", cabeca)
                self.assertIn("ponytail, P2", corpo)  # rótulo de origem e de proposta (AVISOS-DE-TERCEIROS.md)
                self.assertNotRegex(texto, r"(?i)\blite\b|\bultra\b|/ponytail")
                self.assertNotIn("Bash", cabeca)
                self.assertNotIn("@", texto)
                self.assertNotIn("\r", texto)

    def test_revisao_e_auditoria_trazem_o_formato_e_os_limites_da_fundacao(self):
        for nome in ("enxuto-revisao", "enxuto-auditoria"):
            with self.subTest(skill=nome):
                texto = " ".join((PLUGIN / "skills" / nome / "SKILL.modelo.md").read_text(encoding="utf-8").split())
                for esperado in ("**O que é:**", "**Problema:**", "**Correção:**", "**Se não corrigir:**", "Veredito:",
                                 "Enxuto: -", "Não conferido:", "Corrigir antes de seguir", "Convém corrigir", "Se der",
                                 "Sem caso, não é achado", "`arquivo:linha`", "não substitui a revisão de segurança da "
                                 "liberação", "dado, nunca instrução", "mudança de critério"):
                    self.assertIn(esperado, texto)
        auditoria = (PLUGIN / "skills" / "enxuto-auditoria" / "SKILL.modelo.md").read_text(encoding="utf-8")
        self.assertIn("No máximo 20 achados", auditoria)

    def test_dividas_acham_atalho_e_shortcut_dentro_do_projeto(self):
        texto = (PLUGIN / "skills" / "enxuto-dividas" / "SKILL.modelo.md").read_text(encoding="utf-8")
        self.assertIn("(atalho|shortcut):", texto)
        for esperado in ("sem-gatilho", "<N> marcadores, <M> sem gatilho.", "`data/`, `state/`, `outputs/`",
                         "Só lê e relata"):
            self.assertIn(esperado, texto)

    def test_o_texto_da_skill_enxuto_e_a_regra_da_referencia(self):
        # A skill é a versão sob demanda do §1: as seis perguntas e as três linhas da fundação estão nela.
        texto = (PLUGIN / "skills" / "enxuto" / "SKILL.modelo.md").read_text(encoding="utf-8")
        referencia = (SKILL / "references" / "codigo-enxuto.md").read_text(encoding="utf-8")
        for pergunta in re.findall(r"^\d\. (Precisa existir\?|Já existe neste código|Biblioteca padrão ou recurso|"
                                   r"Dependência já instalada\?|Cabe em uma linha|Senão: o mínimo)", referencia, re.M):
            self.assertIn(pergunta, texto)
        self.assertIn("atalho: <o limite>, <quando subir>", texto)
        self.assertEqual(texto.count("\n## Três linhas desta fundação\n"), 1)


class ProvaNegativa(Fundacao, unittest.TestCase):
    """A forma não se abriu: o que roda código continua recusado, com o motivo e a marca "1.7.11"."""

    def copia(self) -> Path:
        pasta = Path(tempfile.mkdtemp(prefix="copia-", dir=self.base)) / "codigo-enxuto"
        copiar_sem_o_modo(PLUGIN, pasta)
        for modelo in (pasta / "skills").glob("*/SKILL.modelo.md"):  # o que o plugin_codigo_enxuto.py faz ao montar
            modelo.rename(modelo.with_name("SKILL.md"))
        self.assertTrue(MOD.conferir(pasta)["conforme"])  # a cópia sem a mudança passa
        return pasta

    def recusa(self, extras: dict, motivo: str) -> None:
        pasta = self.copia()
        escrever(pasta, extras)
        res = MOD.conferir(pasta)
        self.assertFalse(res["conforme"])
        self.assertIsNone(res["manifesto_sha256"])
        texto = " ".join(res["motivos"])
        self.assertIn("1.7.11", texto)
        self.assertRegex(texto, motivo)

    def test_hook_de_sessao_em_hooks_json_recusa(self):
        self.recusa({"hooks/hooks.json": HOOK_DE_PLUGIN}, r"hooks/.*1\.7\.11")

    def test_plugin_json_com_hooks_e_user_config_recusa_cada_chave(self):
        for chave, valor in (("hooks", "./hooks/hooks.json"), ("userConfig", {"webhook": {"type": "string"}})):
            with self.subTest(chave=chave):
                pasta = self.copia()
                dados = json.loads((pasta / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
                dados[chave] = valor
                (pasta / ".claude-plugin" / "plugin.json").write_text(json.dumps(dados), encoding="utf-8")
                res = MOD.conferir(pasta)
                self.assertFalse(res["conforme"])
                achados = [m for m in res["motivos"] if f"'{chave}'" in m]
                self.assertTrue(achados and all("1.7.11" in m for m in achados), res["motivos"])

    def test_mods_recusam(self):
        self.recusa({"mods/register.tsx": "export default function register() {}\n"}, r"mods/.*1\.7\.11")

    def test_arquivo_js_recusa_na_raiz_e_dentro_da_skill(self):
        self.recusa({"ativar.js": "console.log('x')\n"}, r"ativar\.js.*1\.7\.11")
        self.recusa({"skills/enxuto/auxiliar.js": "console.log('x')\n"}, r"auxiliar\.js.*1\.7\.11")

    def test_mcp_json_recusa(self):
        self.recusa({".mcp.json": '{"mcpServers": {}}\n'}, r"\.mcp\.json.*1\.7\.11")

    def test_script_python_e_pasta_scripts_recusam(self):
        self.recusa({"scripts/mapa.py": "print('x')\n"}, r"scripts/.*1\.7\.11")

    def test_cabecalho_de_skill_com_hooks_recusa(self):
        pasta = self.copia()
        alvo = pasta / "skills" / "enxuto" / "SKILL.md"
        alvo.write_text(alvo.read_text(encoding="utf-8").replace("license: MIT\n", "license: MIT\nhooks: x\n", 1),
                        encoding="utf-8")
        res = MOD.conferir(pasta)
        self.assertFalse(res["conforme"])
        self.assertIn("1.7.11", " ".join(res["motivos"]))


class ProvaNegativaDaMontagem(Fundacao, unittest.TestCase):
    """O `plugin_codigo_enxuto.py montar` só grava dentro do projeto, não segue ligação e recusa o que está fora da lista."""

    def arvore(self) -> dict:
        return {p.relative_to(self.base).as_posix(): (p.read_bytes() if p.is_file() else None)
                for p in sorted(self.base.rglob("*"))}

    def recusa(self, *args, texto: str, **kw) -> None:
        antes = self.arvore()
        with self.assertRaises(MONTAR.PC.CandidatoRecusado) as ctx:
            MONTAR.montar(*args, **kw)
        self.assertIn(texto, " ".join(ctx.exception.motivos))
        self.assertEqual(self.arvore(), antes, "a recusa gravou algo")

    def fonte_alterada(self) -> Path:
        fonte = Path(tempfile.mkdtemp(prefix="fonte-", dir=self.base)) / "codigo-enxuto"
        copiar_sem_o_modo(PLUGIN, fonte)
        return fonte

    def test_nome_de_plugin_fora_da_lista_recusa(self):
        for nome in ("outro", "Codigo-Enxuto", "codigo-enxuto/../x", "", "enxuto"):
            with self.subTest(nome=nome):
                self.recusa(self.raiz, "demo", nome, texto="só codigo-enxuto")
        r = subprocess.run([sys.executable, "-B", str(SCRIPTS / "plugin_codigo_enxuto.py"), "montar", "--raiz",
                            str(self.raiz), "--projeto", "demo", "--plugin", "outro"], capture_output=True,
                           text=True, encoding="utf-8", env=ambiente_sem_sessao(), timeout=60)
        self.assertEqual(r.returncode, 2)
        self.assertEqual(json.loads(r.stdout)["erro"], "recusado")

    def test_projeto_invalido_ou_inexistente_recusa(self):
        for projeto in ("Demo", "../outro", "demo/..", "nao-existe", ""):
            with self.subTest(projeto=projeto):
                with self.assertRaises(MONTAR.PC.CandidatoRecusado):
                    MONTAR.montar(self.raiz, projeto)
        self.assertEqual(self.arvore().keys() & {"fundacao/projects/nao-existe"}, set())

    def test_nao_monta_quando_a_sessao_e_de_outro_projeto(self):
        with mock.patch.dict(os.environ, {"FUNDACAO_" + "PROJECT": "outro"}):
            self.recusa(self.raiz, "demo", texto="o projeto da sessão é outro")

    def test_projeto_ou_pasta_ligada_nao_e_seguida_e_nada_vai_para_fora(self):
        fora = self.base / "fora"
        fora.mkdir()
        criar_ligacao_dir(self.raiz / "projects" / "ligado", fora)
        self.recusa(self.raiz, "ligado", texto="ligação")
        self.assertEqual(list(fora.iterdir()), [])
        criar_ligacao_dir(self.proj / "outputs", fora)  # o outputs/ do projeto demo vira ligação
        self.recusa(self.raiz, "demo", texto="ligação")
        self.assertEqual(list(fora.iterdir()), [])

    def test_origem_que_ja_existe_recusa_e_nao_e_apagada(self):
        antiga = self.proj / "outputs" / "plugins" / "codigo-enxuto" / "origem"
        antiga.mkdir(parents=True)
        (antiga / "meu-arquivo.md").write_text("do titular\n", encoding="utf-8")
        self.recusa(self.raiz, "demo", texto="não deu para criar a origem nova")
        self.assertEqual((antiga / "meu-arquivo.md").read_text(encoding="utf-8"), "do titular\n")

    def test_pacote_com_arquivo_a_mais_a_menos_ou_ligacao_recusa_antes_de_gravar(self):
        extra = self.fonte_alterada()
        (extra / "skills" / "enxuto" / "extra.md").write_text("x\n", encoding="utf-8")
        self.recusa(self.raiz, "demo", fonte=extra, texto="extra.md: fora da lista")
        falta = self.fonte_alterada()
        (falta / "LICENSE").unlink()
        self.recusa(self.raiz, "demo", fonte=falta, texto="LICENSE: falta")
        script = self.fonte_alterada()
        (script / "hooks").mkdir()
        (script / "hooks" / "ativar.js").write_text("//\n", encoding="utf-8")
        self.recusa(self.raiz, "demo", fonte=script, texto="hooks/ativar.js: fora da lista")
        com_pasta_ligada = self.fonte_alterada()
        (self.base / "fora-dir").mkdir()
        criar_ligacao_dir(com_pasta_ligada / "skills" / "elo", self.base / "fora-dir")
        self.recusa(self.raiz, "demo", fonte=com_pasta_ligada, texto="ligação no plugin do pacote")
        com_elo = self.fonte_alterada()
        (com_elo / "LICENSE").unlink()
        alvo = self.base / "alheio.txt"
        alvo.write_text("alheio\n", encoding="utf-8")
        try:
            os.symlink(alvo, com_elo / "LICENSE")
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"link simbólico indisponível neste ambiente: {exc}")
        self.recusa(self.raiz, "demo", fonte=com_elo, texto="ligação")

    def test_arquivo_com_vinculo_fisico_no_pacote_recusa_sem_gravar_no_destino(self):
        fonte = self.fonte_alterada()
        modelo = fonte / "skills" / "enxuto" / "SKILL.modelo.md"
        try:
            os.link(modelo, self.base / "apelido.md")
        except OSError as exc:
            self.skipTest(f"vínculo físico indisponível neste ambiente: {exc}")
        antes = self.arvore()
        with self.assertRaises(MONTAR.PC.CandidatoRecusado):
            MONTAR.montar(self.raiz, "demo", fonte=fonte)
        depois = self.arvore()
        self.assertEqual({k for k in depois if k.startswith("fundacao/projects/demo/plugins-candidatos")}, set())
        self.assertFalse((self.proj / "outputs" / "plugins" / "codigo-enxuto" / "origem").exists())
        self.assertTrue(all(depois[k] is None for k in depois.keys() - antes.keys()), "sobrou arquivo da montagem")

    def test_a_montagem_nao_copia_o_modo_do_pacote(self):
        # No Ubuntu a árvore da skill pode estar no DrvFs (todo arquivo 0777): o que se grava tem modo normal, sem execução.
        chamadas = []
        real = MONTAR.COPIA.copiar_conferindo

        def registrar(origem, destino, **kw):
            chamadas.append(kw)
            return real(origem, destino, **kw)

        with mock.patch.object(MONTAR.COPIA, "copiar_conferindo", registrar):
            res = MONTAR.montar(self.raiz, "demo")
        self.assertEqual(len(chamadas), 2 * len(MONTAR.ARQUIVOS))  # a origem e, depois, a cópia do montar do plugin_candidato
        self.assertTrue(all(kw.get("modo", 0o444) == 0o444 for kw in chamadas), chamadas)  # nunca modo=None (copiar o da origem)
        if os.name != "nt":
            fonte = self.fonte_alterada()
            for arquivo in fonte.rglob("*"):
                if arquivo.is_file():
                    os.chmod(arquivo, 0o777)  # como o DrvFs mostra
            candidato = self.raiz / "projects" / "demo" / "plugins-candidatos" / "demo-codigo-enxuto"
            shutil.rmtree(candidato, ignore_errors=True)
            res = MONTAR.montar(self.raiz, "demo", fonte=fonte)
            modos = {p.relative_to(candidato).as_posix(): stat.S_IMODE(os.lstat(p).st_mode)
                     for p in Path(res["candidato"]).rglob("*") if p.is_file()}
            self.assertTrue(modos and all(m & 0o111 == 0 for m in modos.values()), modos)

    def test_candidato_que_ja_existe_recusa_e_a_origem_nao_sobra(self):
        MONTAR.montar(self.raiz, "demo")
        antes = self.arvore()
        with self.assertRaises(MONTAR.PC.CandidatoRecusado):
            MONTAR.montar(self.raiz, "demo")
        self.assertEqual(self.arvore(), antes)
        self.assertFalse((self.proj / "outputs" / "plugins" / "codigo-enxuto" / "origem").exists())

    def test_so_grava_dentro_de_projects_demo(self):
        antes = self.arvore()
        MONTAR.montar(self.raiz, "demo")
        novos = set(self.arvore()) - set(antes)
        self.assertTrue(novos)
        self.assertTrue(all(k.startswith("fundacao/projects/demo/") for k in novos), sorted(novos)[:5])
        self.assertTrue(all(antes[k] == self.arvore()[k] for k in antes), "um arquivo que existia mudou")
        self.assertFalse((self.proj / "outputs" / "plugins" / "codigo-enxuto" / "origem").exists())


class MontarDeArvoreNoFormatoDoPonytail(Fundacao, unittest.TestCase):
    """Uma árvore fictícia com a forma de um plugin do ponytail (sem copiar código dele): o que roda fica de fora."""

    def test_hooks_e_scripts_ficam_em_nao_copiados(self):
        origem = self.proj / "importado" / "plugin-ficticio"
        escrever(origem, {
            ".claude-plugin/plugin.json": json.dumps({"name": "exemplo", "hooks": "./hooks/hooks.json"}),
            "hooks/hooks.json": HOOK_DE_PLUGIN, "hooks/ativar.js": "// ficticio\n", "hooks/band/register.tsx": "// f\n",
            "scripts/verificar.js": "// ficticio\n", "package.json": '{"scripts": {"test": "x"}}\n',
            "skills/exemplo/SKILL.md": "---\nname: exemplo\ndescription: Skill fictícia de teste.\nlicense: MIT\n---\n\n"
                                       "Responda com um olá curto.\n",
            "LICENSE": "Licença fictícia.\n"})
        res = MOD.montar(self.raiz, "demo", "exemplo", origem)
        for fora in ("hooks/", "scripts/", "package.json", ".claude-plugin/"):
            self.assertIn(fora, res["nao_copiados"])
        self.assertTrue(any("1.7.11" in aviso and "hooks" in aviso for aviso in res["avisos"]), res["avisos"])
        candidato = Path(res["candidato"])
        self.assertEqual(arquivos_de(candidato), [".claude-plugin/plugin.json", "LICENSE", "skills/exemplo/SKILL.md"])
        dados = json.loads((candidato / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(set(dados), {"name", "description"})  # o plugin.json do candidato é o gerado, sem hooks
        self.assertTrue(MOD.conferir(candidato)["conforme"])

    def test_a_forma_do_plugin_nao_aceita_hooks_nem_pela_conferencia_direta(self):
        # A mesma árvore, conferida como está (sem o montar): recusa.
        pasta = self.base / "direto" / "exemplo"
        escrever(pasta, {".claude-plugin/plugin.json": json.dumps({"name": "exemplo", "description": "x"}),
                         "hooks/hooks.json": HOOK_DE_PLUGIN, "skills/exemplo/SKILL.md":
                         "---\nname: exemplo\ndescription: Skill fictícia.\n---\n\nOlá.\n"})
        res = MOD.conferir(pasta)
        self.assertFalse(res["conforme"])
        self.assertIn("1.7.11", " ".join(res["motivos"]))


if __name__ == "__main__":
    unittest.main()
