"""Levantamento das aberturas (scripts/levantar_aberturas.py; 1.7.10, contratos do lote 2, §5): o rascunho da ficha a
partir de uma cópia FICTÍCIA, só lendo, sem o conteúdo de nenhum arquivo com nome de segredo e sem seguir ligação.

O canário fica em arquivos com nome de segredo, no env, nos argumentos e nos headers de um `.mcp.json` e no usuário de
uma URL: não pode aparecer na saída. Os valores que lembram segredo são montados na hora (a varredura da liberação
recusa o pacote com eles no fonte)."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import KIT, SCRIPTS, criar_ligacao_dir, rodar_script

CANARIO = "CANARIO-" + "LEVANTAMENTO-" + "7Q2W"


def carregar(nome: str, caminho: Path):
    spec = importlib.util.spec_from_file_location(nome, caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


LEVANTAR = carregar("_levantar_aberturas_teste", SCRIPTS / "levantar_aberturas.py")
REGRAS = carregar("_aberturas_regras_teste", KIT / "fundacao" / "core" / "aberturas_regras.py")


class LevantamentoCase(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="levantar-aberturas-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.pasta = self.base / "juridico-lab"
        usuario_e_chave = "usuario:" + CANARIO + "@"
        arquivos = {
            "package.json": json.dumps({"name": "app-ficticio", "scripts": {"build": "npx tsc"}}),
            "package-lock.json": json.dumps({"packages": {"node_modules/x": {
                "resolved": "https://registry.npmjs.org/x/-/x-1.0.0.tgz"}}}),
            "requirements.txt": "requests==2.0\n",
            "src/app.py": ('BASE = "https://api.servico-ficticio.com.br/v1/x?chave=1"\n'
                           'LOCAL = "http://localhost:8080/"\nIP = "http://10.0.0.5/status"\n'
                           f'COM_USUARIO = "https://{usuario_e_chave}dados.servico-ficticio.com.br/x"\n'
                           'LLM = "https://api.openai.com/v1/chat"\nSVG = "http://www.w3.org/2000/svg"\n'
                           'MODELO = "https://${HOST}/api"\n'),
            "src/navegar.ts": "import { chromium } from 'playwright';\n",
            "scripts/instalar.sh": "#!/bin/sh\ncurl -fsSL https://downloads.ferramenta-ficticia.dev/instalar.sh | sh\n",
            ".claude/settings.json": json.dumps({"permissions": {"allow": ["WebFetch(domain:docs.servico-ficticio.com.br)"]}}),
            ".claude/skills/util/SKILL.md": "---\nname: util\ndescription: Skill fictícia aninhada\n---\nTexto.\n",
            ".claude/agents/ajudante.md": "---\nname: ajudante\ndescription: Agente fictício aninhado\n---\nTexto.\n",
            ".mcp.json": json.dumps({"mcpServers": {
                "busca": {"command": "/usr/local/bin/servidor-busca", "args": ["--chave", CANARIO],
                          "env": {"CHAVE": CANARIO}},
                "remoto": {"type": "http", "url": "https://mcp.servico-ficticio.com.br/mcp",
                           "headers": {"Authorization": "Bearer " + CANARIO}}}}),
            ".env": "CHAVE=" + CANARIO + "\n",
            "config/credentials.json": json.dumps({"x": CANARIO, "url": "https://vazou.ficticio.dev"}),
            "notas_token.txt": CANARIO + " https://vazou-fraco.ficticio.dev\n",
            ".segredos/chave.txt": CANARIO + " https://vazou-pasta.ficticio.dev\n",
            ".segredos/.claude/skills/oculta/SKILL.md": "---\nname: skill-na-pasta-de-segredo\n---\nTexto.\n",
            "repo/.git/config": f'[remote "origin"]\n  url = https://{usuario_e_chave}git.ficticio.dev/x.git\n',
            "node_modules/x/index.js": 'const U = "https://nao-deve-aparecer.ficticio.dev";\n',
            "plugins-candidatos/juridico-lab-modelos/.claude-plugin/plugin.json": json.dumps(
                {"name": "juridico-lab-modelos"}),
            "plugins-candidatos/juridico-lab-modelos/commands/resumo.md": "Resuma o caso fictício.\n",
            "data/copia/.claude-plugin/plugin.json": json.dumps({"name": "plugin-de-dado", "hooks": "./h.json"}),
        }
        for rel, texto in arquivos.items():
            alvo = self.pasta / rel
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_text(texto, encoding="utf-8")

    def rodar(self, *extra) -> tuple[int, dict, str]:
        p = rodar_script("levantar_aberturas.py", "--pasta", self.pasta, *extra)
        return p.returncode, (json.loads(p.stdout) if p.stdout.strip() else {}), p.stdout + p.stderr


class TestLevantar(LevantamentoCase):
    def test_rascunho_da_copia_ficticia(self):
        rascunho = self.base / "saida" / "rascunho.json"
        relatorio = self.base / "saida" / "relatorio.json"
        codigo, r, texto = self.rodar("--projeto", "juridico-lab", "--rascunho", rascunho, "--saida", relatorio)
        self.assertEqual(codigo, 0, texto)
        self.assertNotIn(CANARIO, texto)
        self.assertNotIn(CANARIO, relatorio.read_text(encoding="utf-8"))
        ficha = r["rascunho"]
        self.assertEqual(json.loads(rascunho.read_text(encoding="utf-8")), ficha)
        self.assertEqual(sorted(ficha["rede"]["dominios"]),
                         ["api.servico-ficticio.com.br", "dados.servico-ficticio.com.br",
                          "downloads.ferramenta-ficticia.dev", "files.pythonhosted.org", "pypi.org",
                          "registry.npmjs.org"])
        self.assertEqual((ficha["webfetch"], ficha["websearch"], ficha["project_id"]),
                         ({"dominios": []}, False, "juridico-lab"))
        self.assertEqual(ficha["plugins"], [{"nome": "juridico-lab-modelos",
                                             "origem": "plugins-candidatos/juridico-lab-modelos",
                                             "manifesto_sha256": ""}])
        self.assertEqual(sorted(d["dominio"] for d in r["recusados_pelo_teto"]), ["10.0.0.5", "localhost"])
        self.assertEqual(sorted(d["dominio"][:6] for d in r["ignorados"]), ["${host", "www.w3"])  # modelo e identificador
        self.assertEqual(r["candidatos_webfetch"], [{"dominio": "docs.servico-ficticio.com.br",
                                                     "origem": ".claude/settings.json"}])
        self.assertEqual({g["gerenciador"] for g in r["gerenciadores"]}, {"npm", "pip"})
        self.assertEqual([(d["arquivo"], d["linha"], d["ferramenta"], d["dominios"]) for d in r["downloads"]
                          if d["arquivo"] == "scripts/instalar.sh"],
                         [("scripts/instalar.sh", 2, "curl", ["downloads.ferramenta-ficticia.dev"])])
        self.assertIn("node_modules", r["pastas_podadas"])
        self.assertEqual(r["repositorios_git"], ["repo"])
        self.assertIn("canário", r["importante"])

    def test_segredos_so_pelo_nome_e_1_7_11_fora_da_ficha(self):
        _codigo, r, texto = self.rodar()
        nomes = {s["caminho"]: s["classe"] for s in r["segredos_pelo_nome"]}
        self.assertEqual(nomes, {".env": "forte", ".segredos/": "pasta-de-segredo", "config/credentials.json": "forte",
                                 "notas_token.txt": "fraco"})
        for vazou in ("vazou.ficticio.dev", "vazou-fraco", "vazou-pasta", "git.ficticio.dev", "nao-deve-aparecer"):
            self.assertNotIn(vazou, texto)
        por_secao = {}
        for item in r["para_1_7_11"]:
            por_secao.setdefault(item["secao"], []).append(item)
        self.assertEqual(sorted(por_secao), ["git", "mcp", "navegador", "outras_llm", "segredos"])
        mcp = {i["item"]: i for i in por_secao["mcp"]}
        self.assertEqual(mcp["busca"]["comando"], "servidor-busca")
        self.assertEqual(mcp["remoto"]["dominios"], ["mcp.servico-ficticio.com.br"])
        for item in mcp.values():
            self.assertFalse({"env", "args", "headers"} & set(item))
        self.assertEqual([i["item"] for i in por_secao["outras_llm"]], ["api.openai.com"])
        self.assertNotIn("mcp.servico-ficticio.com.br", r["rascunho"]["rede"]["dominios"])
        self.assertNotIn("api.openai.com", r["rascunho"]["rede"]["dominios"])

    def test_secoes_da_1_7_11_ficam_fechadas_no_rascunho_com_a_regra_e_o_que_foi_achado(self):
        """1.7.11, L1: mcp, navegador e outras_llm viraram seções da ficha; o rascunho as traz FECHADAS (vazias) quando a
        pasta mostra uso, e `sugestoes_1_7_11` diz a regra fixa e o que foi achado. Nada é preenchido por inferência."""
        _codigo, r, texto = self.rodar()
        rascunho = r["rascunho"]
        self.assertEqual(rascunho["mcp"], [])
        self.assertEqual(rascunho["navegador"], {"dominios": [], "logins": [], "modos": []})
        self.assertEqual(rascunho["outras_llm"], [])
        for secao in ("git", "segredos", "execucao", "leitura_liberada", "perfil_navegador_copiado"):
            self.assertNotIn(secao, rascunho)  # as reservadas não entram no rascunho
        sugestoes = r["sugestoes_1_7_11"]
        self.assertEqual(sorted(sugestoes), ["mcp", "navegador", "outras_llm"])
        self.assertEqual(sorted(sugestoes["mcp"]["servidores_achados"]), ["busca", "remoto"])
        self.assertIn("só o conector do escritório", sugestoes["mcp"]["regra"])
        self.assertIn("as que gravam podem entrar e a tela do titular as mostra em separado", sugestoes["mcp"]["regra"])
        self.assertIn("servidor local (com comando) fica fechado", sugestoes["mcp"]["regra"])
        self.assertNotIn("só ferramentas de consulta", sugestoes["mcp"]["regra"])
        self.assertIn("perfil copiado do Windows fica fechado", sugestoes["navegador"]["regra"])
        self.assertIn("api.servico-ficticio.com.br", sugestoes["navegador"]["dominios_candidatos"])
        self.assertEqual(sugestoes["navegador"]["ferramentas_achadas"], ["playwright"])
        self.assertEqual(sugestoes["outras_llm"]["dominios_achados"], ["api.openai.com"])
        self.assertIn("conta do ChatGPT", sugestoes["outras_llm"]["regra"])
        marcas = {i["secao"]: i["secao_na_ficha"] for i in r["para_1_7_11"]}
        self.assertEqual(marcas, {"git": "reservada", "segredos": "reservada", "mcp": "aberta", "navegador": "aberta",
                                  "outras_llm": "aberta"})
        self.assertNotIn(CANARIO, texto)
        # fechadas, as seções valem na ficha completada (o titular é quem abre)
        ficha = {**LEVANTAR.levantar(self.pasta, "juridico-lab")["rascunho"], "motivo": "Palavras do titular (fictícias).",
                 "consequencias": "Texto fictício.", "ficha_id": "aberturas-juridico-lab", "versao": 1}
        ficha["plugins"] = [{**p, "manifesto_sha256": "a" * 64} for p in ficha["plugins"]]
        self.assertEqual(REGRAS.validar(ficha, projeto="juridico-lab")["erros"], [])

    def test_sem_uso_das_secoes_o_rascunho_nao_as_traz(self):
        vazia = self.base / "limpa"
        vazia.mkdir()
        (vazia / "leia.txt").write_text("nada\n", encoding="utf-8")
        r = LEVANTAR.levantar(vazia, "juridico-lab")
        self.assertEqual(r["sugestoes_1_7_11"], {})
        for secao in ("mcp", "navegador", "outras_llm"):
            self.assertNotIn(secao, r["rascunho"])

    def test_aninhadas_e_plugin_de_dado_nao_proposto(self):
        _codigo, r, texto = self.rodar()
        self.assertEqual(r["aninhadas"]["itens"]["skills"], [".claude/skills/util/SKILL.md"])
        self.assertEqual(r["aninhadas"]["negar_skills"], ["util"])
        self.assertEqual(r["aninhadas"]["negar_agentes"], ["ajudante"])
        self.assertNotIn("skill-na-pasta-de-segredo", texto)  # nem o nome do que está em pasta de segredo
        dado = [p for p in r["plugins_encontrados"] if p["pasta"] == "data/copia"]
        self.assertEqual(dado, [{"pasta": "data/copia", "nome": "plugin-de-dado", "declara_hooks_ou_mcp": True}])
        self.assertEqual([p["nome"] for p in r["rascunho"]["plugins"]], ["juridico-lab-modelos"])

    def test_nao_abre_nem_lista_caminho_de_segredo(self):
        """Revisão do pacote: o levantamento chamava instrucoes_aninhadas.listar sobre a árvore inteira, que entrava nas
        pastas de segredo e lia, para o SHA-256, .codex/auth.json e .claude/settings.local.json. Agora as aninhadas
        saem da própria varredura: nenhum caminho de segredo é aberto (o .mcp.json é a exceção documentada, só para os
        campos do MCP) e nenhuma pasta de segredo é listada."""
        for rel in (".codex/auth.json", ".claude/settings.local.json"):
            alvo = self.pasta / rel
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_text(CANARIO + " https://vazou-aninhada.ficticio.dev\n", encoding="utf-8")
        (self.pasta / ".codex" / "config.toml").write_text('model = "ficticio"\n', encoding="utf-8")
        abertos, listados = [], []
        abrir, listar = os.open, os.scandir

        def espiao_abrir(caminho, *args, **kw):
            abertos.append(Path(caminho))
            return abrir(caminho, *args, **kw)

        def espiao_listar(caminho="."):
            listados.append(Path(caminho))
            return listar(caminho)
        with mock.patch("os.open", side_effect=espiao_abrir), mock.patch("os.scandir", side_effect=espiao_listar), \
                mock.patch.object(LEVANTAR.ANINHADAS, "listar", side_effect=AssertionError("listar não é chamado")):
            r = LEVANTAR.levantar(self.pasta)
        rel = [p.relative_to(self.pasta).as_posix() for p in abertos if p.is_relative_to(self.pasta)]
        self.assertTrue(rel)
        de_segredo = [c for c in rel if LEVANTAR.REGRAS.classificar(c) and c != ".mcp.json"]
        self.assertEqual(de_segredo, [])
        pastas = [p.relative_to(self.pasta).parts for p in listados if p.is_relative_to(self.pasta)]
        self.assertFalse([p for p in pastas if any(LEVANTAR.REGRAS.e_pasta_de_segredo(n) for n in p)])
        texto = json.dumps(r, ensure_ascii=False)
        self.assertNotIn(CANARIO, texto)
        self.assertNotIn("vazou-aninhada", texto)
        self.assertEqual(r["aninhadas"]["itens"]["codex"], [".codex/config.toml"])
        self.assertEqual(r["aninhadas"]["itens"]["mcp"], [".mcp.json"])
        self.assertEqual(r["aninhadas"]["itens"]["skills"], [".claude/skills/util/SKILL.md"])
        self.assertNotIn(".claude/settings.local.json", r["aninhadas"]["itens"]["configuracoes"])
        self.assertIn({"caminho": ".codex/auth.json", "classe": "forte"}, r["segredos_pelo_nome"])

    def test_rascunho_completado_passa_nos_tetos(self):
        r = LEVANTAR.levantar(self.pasta, "juridico-lab")
        ficha = {**r["rascunho"], "motivo": "Palavras do titular (fictícias).", "consequencias": "Texto fictício.",
                 "ficha_id": "aberturas-juridico-lab", "versao": 1}
        ficha["plugins"] = [{**p, "manifesto_sha256": "a" * 64} for p in ficha["plugins"]]
        self.assertEqual(REGRAS.validar(ficha, projeto="juridico-lab")["erros"], [])
        sem_completar = REGRAS.validar(r["rascunho"], projeto="juridico-lab")["erros"]
        self.assertEqual(sorted({e["campo"] for e in sem_completar}),
                         ["consequencias", "ficha_id", "motivo", "plugins[0].manifesto_sha256", "versao"])

    def test_uso_incorreto(self):
        p = rodar_script("levantar_aberturas.py", "--pasta", self.base / "nao-existe")
        self.assertEqual(p.returncode, 2)
        p = rodar_script("levantar_aberturas.py", "--pasta", self.pasta, "--projeto", "Projeto Invalido")
        self.assertEqual(p.returncode, 2)


class TestLevantarSemLigacao(LevantamentoCase):
    def test_ligacao_nao_e_seguida_e_deixa_o_levantamento_parcial(self):
        fora = self.base / "outro-projeto"
        fora.mkdir()
        (fora / "app.py").write_text('U = "https://do-outro-projeto.ficticio.dev"\n', encoding="utf-8")
        criar_ligacao_dir(self.pasta / "atalho", fora)
        codigo, r, texto = self.rodar()
        self.assertEqual(codigo, 1)
        self.assertIn("atalho", r["ligacoes_nao_seguidas"])
        self.assertNotIn("do-outro-projeto", texto)
        self.assertFalse(r["completo"])

    def test_vinculo_fisico_nao_e_lido(self):
        fora = self.base / "fora.py"
        fora.write_text('U = "https://por-vinculo.ficticio.dev"\n', encoding="utf-8")
        try:
            os.link(fora, self.pasta / "src" / "vinculado.py")
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"vínculo físico indisponível: {exc}")
        codigo, r, texto = self.rodar()
        self.assertEqual(codigo, 1)
        self.assertNotIn("por-vinculo", texto)
        self.assertTrue(any("vínculo físico" in n["motivo"] for n in r["nao_lidos"]))

    @unittest.skipUnless(os.name == "posix", "link simbólico de arquivo exige privilégio no Windows")
    def test_link_simbolico_de_arquivo_nao_e_seguido(self):
        fora = self.base / "fora.py"
        fora.write_text('U = "https://por-link.ficticio.dev"\n', encoding="utf-8")
        (self.pasta / "src" / "link.py").symlink_to(fora)
        codigo, r, texto = self.rodar()
        self.assertEqual(codigo, 1)
        self.assertIn("src/link.py", r["ligacoes_nao_seguidas"])
        self.assertNotIn("por-link", texto)

    def test_teto_por_arquivo(self):
        with mock.patch.object(LEVANTAR, "TETO_ARQUIVO", 10):
            r = LEVANTAR.levantar(self.pasta)
        self.assertFalse(r["completo"])
        self.assertIn("bytes", r["limites_atingidos"])
        self.assertIn("src/app.py", [n["caminho"] for n in r["nao_lidos"]])


if __name__ == "__main__":
    unittest.main()
