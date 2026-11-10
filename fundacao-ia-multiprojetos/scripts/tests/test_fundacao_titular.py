"""Ferramenta fixa do titular (assets/host/fundacao_titular.py; 1.7.10, contratos do lote 2, §5).

A ferramenta usa o kit da própria skill, confere que o validador do kit da raiz é idêntico, mostra o que a ficha abre
por código fixo, exige o nome do projeto digitado e assina com `ssh-keygen -Y sign -n fundacao-abertura`, gravando na
caixa de entrada sem seguir ligação. Raiz, chaves e âncora de ENSAIO em pastas temporárias (chave sem senha, gerada
na hora); a confirmação é injetada; a âncora padrão desta máquina é trocada pela de ensaio. Sem `ssh-keygen`, pula."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from apoio import KIT, SKILL, criar_ligacao_dir

FERRAMENTA = SKILL / "assets" / "host" / "fundacao_titular.py"
HOJE = date(2026, 10, 31)
PROJETO = "juridico-lab"


def carregar():
    spec = importlib.util.spec_from_file_location("_fundacao_titular_teste", FERRAMENTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


TITULAR = carregar()
K = TITULAR.kit()


def ficha(**extra) -> dict:
    base = {"schema_version": K.regras.SCHEMA, "ficha_id": "aberturas-juridico-lab", "project_id": PROJETO,
            "versao": 1, "motivo": "Liberar o registro de pacotes.\nPalavras do titular (fictícias).",
            "consequencias": "Os comandos da sessão acessam o registro de pacotes.",
            "rede": {"dominios": ["pypi.org", "files.pythonhosted.org"]}}
    base.update(extra)
    return base


class TitularCase(unittest.TestCase):
    def setUp(self):
        try:
            self.keygen = K.decisoes.ssh_keygen()
        except FileNotFoundError as exc:
            self.skipTest(f"ssh-keygen indisponível neste ambiente: {exc}")
        self.base = Path(tempfile.mkdtemp(prefix="fundacao-titular-teste-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.raiz = self.base / "raiz"
        shutil.copytree(KIT / "fundacao", self.raiz / "fundacao", ignore=shutil.ignore_patterns("__pycache__"))
        self.projeto = self.raiz / "projects" / PROJETO
        self.rascunhos = self.projeto / "outputs" / "aberturas"
        self.rascunhos.mkdir(parents=True)
        self.chaves = self.base / "chaves"
        self.chaves.mkdir()
        for nome in ("titular-ensaio", "intruso"):
            subprocess.run([self.keygen, "-q", "-t", "ed25519", "-N", "", "-C", nome, "-f", str(self.chaves / nome)],
                           check=True, capture_output=True)
        self.ancora = self.base / "ancora" / "allowed_signers"
        self.ancora.parent.mkdir()
        self.escrever_ancora("fundacao-decisao,fundacao-abertura")
        padrao = mock.patch.object(K.decisoes, "ANCORAS_PADRAO", (str(self.ancora),))
        padrao.start()
        self.addCleanup(padrao.stop)
        # A área do titular do Linux (/etc/fundacao-ia/...) trocada por uma de ensaio: nada da máquina é lido.
        self.area = self.base / "etc" / PROJETO / "ficha"
        area = mock.patch.object(K.aberturas, "AREA_DO_TITULAR", str(self.base / "etc" / "{projeto}" / "ficha"))
        area.start()
        self.addCleanup(area.stop)
        self.caixa = K.aberturas.caixa_de_entrada(self.raiz, PROJETO)
        self.perguntas = []

    def escrever_ancora(self, namespaces: str) -> None:
        pub = (self.chaves / "titular-ensaio.pub").read_text(encoding="ascii").strip()
        self.ancora.write_text(f'titular-ensaio namespaces="{namespaces}" {pub}\n', encoding="ascii")

    def preparar(self, f: dict | None = None) -> Path:
        f = f or ficha()
        alvo = self.rascunhos / f"ficha-v{f['versao']}.json"
        alvo.write_bytes(K.regras.canonico(f))
        return alvo

    def assinar(self, resposta: str = PROJETO, **kw) -> tuple[int, str]:
        saida = io.StringIO()

        def confirmar(texto):
            self.perguntas.append(texto)
            return resposta
        kw.setdefault("chave", self.chaves / "titular-ensaio")
        codigo = TITULAR.assinar_ficha(self.raiz, PROJETO, confirmar=confirmar, saida=saida, hoje=HOJE, **kw)
        return codigo, saida.getvalue()

    def recusa(self, trecho: str, **kw) -> None:
        with self.assertRaises(TITULAR.Recusa) as ctx:
            self.assinar(**kw)
        self.assertIn(trecho.casefold(), str(ctx.exception).casefold())
        self.assertFalse(self.caixa.exists() and any(p.suffix == ".json" for p in self.caixa.iterdir()))

    def instalar_na_area(self, versao: int = 1) -> None:
        """O que o preparo do host (sudo) faz no Ubuntu: copia a ficha e o .sig da caixa de entrada para a área."""
        self.area.mkdir(parents=True, exist_ok=True)
        for nome in (f"ficha-v{versao}.json", f"ficha-v{versao}.json.sig"):
            shutil.copyfile(self.caixa / nome, self.area / nome)


class TestAssinarFicha(TitularCase):
    def test_assina_grava_na_caixa_de_entrada_e_a_ficha_vale(self):
        rascunho = self.preparar()
        codigo, texto = self.assinar()
        self.assertEqual(codigo, 0, texto)
        gravada = self.caixa / "ficha-v1.json"
        self.assertEqual(gravada.read_bytes(), rascunho.read_bytes())
        self.assertTrue(Path(str(gravada) + ".sig").is_file())
        r = K.aberturas.vigente(self.raiz, PROJETO, self.caixa, hoje=HOJE)
        self.assertEqual((r["valida"], r["versao"]), (True, 1), r)
        for trecho in ("pypi.org", "files.pythonhosted.org", "passa a abrir: rede files.pythonhosted.org, rede pypi.org",
                       "deixa de abrir: nada", "escrito pela sessão", "    | Palavras do titular (fictícias).",
                       "canário", "Sem data de validade", "Assinada pela chave de titular-ensaio",
                       "esta ficha também vale se houver o seu aceite de risco"):  # 1.7.10.1, R17101-ACE-2
            self.assertIn(trecho, texto)
        self.assertEqual(len(self.perguntas), 1)
        self.assertIn(f"digite o nome do projeto ({PROJETO})", self.perguntas[0])

    def test_confirmacao_errada_nao_grava_nada(self):
        self.preparar()
        for resposta in ("", "sim", "reversa-lab", None):
            with self.subTest(resposta=resposta):
                codigo, texto = self.assinar(resposta=resposta)
                self.assertEqual(codigo, 1)
                self.assertIn("nada foi assinado", texto)
                self.assertFalse(self.caixa.exists())
        for interrupcao in (EOFError, KeyboardInterrupt):
            with self.subTest(interrupcao=interrupcao.__name__):
                saida = io.StringIO()

                def confirmar(_texto, erro=interrupcao):
                    raise erro
                self.assertEqual(TITULAR.assinar_ficha(self.raiz, PROJETO, chave=self.chaves / "titular-ensaio",
                                                       confirmar=confirmar, saida=saida, hoje=HOJE), 1)
                self.assertFalse(self.caixa.exists())

    def test_sem_terminal_interativo_recusa(self):
        self.preparar()
        with mock.patch.object(TITULAR.sys.stdin, "isatty", return_value=False):
            with self.assertRaises(TITULAR.Recusa) as ctx:
                TITULAR.assinar_ficha(self.raiz, PROJETO, chave=self.chaves / "titular-ensaio", hoje=HOJE)
            self.assertIn("sem terminal interativo", str(ctx.exception))
            with mock.patch.object(TITULAR.sys, "stderr", io.StringIO()) as erro:
                self.assertEqual(TITULAR.main(["assinar-ficha", "--raiz", str(self.raiz), "--projeto", PROJETO]), 2)
            self.assertIn("sem terminal interativo", erro.getvalue())

    def test_ficha_fora_dos_tetos_vencida_ou_de_plugin_com_hooks_recusa(self):
        casos = ((ficha(rede={"dominios": ["*.vercel.app"]}), "tetos"),
                 (ficha(vigencia_ate="2026-10-30"), "vencida"),
                 (ficha(webfetch={"dominios": ["docs.ficticio.com.br"]}), "rede.dominios"),
                 (ficha(git=[{"pasta": "repo"}]), "1.7.11"),
                 (ficha(navegador={"dominios": ["esaj.tjsp.jus.br"], "modos": ["sessao"], "perfil": "copiado"}),
                  "navegador.perfil"),
                 (ficha(mcp=[{"nome": "fsn", "origem": "conta", "conector": "Conector do escritorio",
                              "ferramentas": ["buscar_*"], "conteudo_de_terceiros": True}]), "mcp[0].ferramentas[0]"),
                 (ficha(mcp=[{"nome": "fsn", "origem": "conta", "conector": "Conector do escritorio",
                              "ferramentas": ["buscar_clientes"], "comando": "npx", "conteudo_de_terceiros": True}]),
                  "mcp[0].comando"),
                 (ficha(project_id="reversa-lab"), "outro projeto"))
        for f, trecho in casos:
            with self.subTest(trecho=trecho):
                self.preparar(f)
                self.recusa(trecho)
        plugin = self.projeto / "plugins-candidatos" / "juridico-lab-modelos"
        (plugin / ".claude-plugin").mkdir(parents=True)
        (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "juridico-lab-modelos"}),
                                                               encoding="utf-8")
        (plugin / "hooks").mkdir()
        self.preparar(ficha(plugins=[{"nome": "juridico-lab-modelos", "origem": "plugins-candidatos/juridico-lab-modelos",
                                      "manifesto_sha256": "a" * 64}]))
        self.recusa("1.7.11")
        self.assertEqual(self.perguntas, [])  # recusa antes de mostrar e de pedir a confirmação

    def test_plugin_com_manifesto_diferente_do_disco_recusa(self):
        plugin = self.projeto / "plugins-candidatos" / "juridico-lab-modelos"
        (plugin / ".claude-plugin").mkdir(parents=True)
        (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "juridico-lab-modelos"}),
                                                               encoding="utf-8")
        item = {"nome": "juridico-lab-modelos", "origem": "plugins-candidatos/juridico-lab-modelos"}
        certo = K.plugins.conferir_pasta_do_plugin(plugin, "juridico-lab-modelos")["manifesto_sha256"]
        self.preparar(ficha(plugins=[{**item, "manifesto_sha256": certo}]))
        self.assertEqual(self.assinar()[0], 0)
        (plugin / "commands").mkdir()
        (plugin / "commands" / "novo.md").write_text("Comando acrescentado depois (fictício).\n", encoding="utf-8")
        self.preparar(ficha(versao=2, plugins=[{**item, "manifesto_sha256": certo}]))
        with self.assertRaises(TITULAR.Recusa) as ctx:
            self.assinar()
        self.assertIn("mudou", str(ctx.exception))
        self.assertFalse((self.caixa / "ficha-v2.json").exists())

    def test_kit_da_raiz_diferente_ou_sem_o_validador_recusa(self):
        self.preparar()
        regras_da_raiz = self.raiz / "fundacao" / "core" / "aberturas_regras.py"
        regras_da_raiz.write_bytes(regras_da_raiz.read_bytes() + b"\n# alterado na raiz\n")
        self.recusa("difere")
        regras_da_raiz.unlink()
        self.recusa("não tem")

    def test_kit_da_raiz_com_outro_aberturas_markdown_recusa(self):
        # Integração, rodada 2 (item I16): as regras de cada Markdown do plugin saíram do aberturas_plugins.py para o
        # aberturas_markdown.py, que entrou no VALIDADOR; sem ele, uma regra diferente na raiz passava sem aviso.
        self.preparar()
        markdown_da_raiz = self.raiz / "fundacao" / "core" / "aberturas_markdown.py"
        markdown_da_raiz.write_bytes(markdown_da_raiz.read_bytes() + b"\n# alterado na raiz\n")
        self.recusa("aberturas_markdown.py do kit da raiz difere")

    def test_kit_da_raiz_com_outro_manutencao_ou_contracts_recusa(self):
        # Revisão da integração, rodada 2: o manutencao.py (de onde saem as listas de nome forte e de pasta de segredo
        # da regra do plugin) e o contracts.py (que o aberturas_plugins importa) entraram no VALIDADOR; antes, um kit
        # da raiz com outras listas aplicava, no abertura preparar, outra regra de segredo sem aviso.
        self.preparar()
        for nome in ("manutencao.py", "contracts.py"):
            with self.subTest(nome=nome):
                da_raiz = self.raiz / "fundacao" / "core" / nome
                original = da_raiz.read_bytes()
                da_raiz.write_bytes(original + b"\n# alterado na raiz\n")
                self.recusa(f"{nome} do kit da raiz difere")
                da_raiz.unlink()
                self.recusa("não tem")
                da_raiz.write_bytes(original)
        self.assertEqual(self.assinar()[0], 0, "com o kit da raiz igual, assina")

    def test_nao_executa_codigo_do_kit_da_raiz(self):
        self.preparar()
        marca = self.base / "executou-o-kit-da-raiz"
        inicio = self.raiz / "fundacao" / "__init__.py"
        inicio.write_text(inicio.read_text(encoding="utf-8") + "\nfrom pathlib import Path as _P\n"
                          f"_P({str(marca)!r}).write_text('x')\n", encoding="utf-8")
        self.assertEqual(self.assinar()[0], 0)
        self.assertFalse(marca.exists())

    def test_mesma_versao_ja_assinada_igual_ou_com_outro_conteudo(self):
        self.preparar()
        self.assertEqual(self.assinar()[0], 0)
        sig = Path(str(self.caixa / "ficha-v1.json") + ".sig").read_bytes()
        codigo, texto = self.assinar()
        self.assertEqual(codigo, 0)
        self.assertIn("já está assinada", texto)
        self.assertEqual(Path(str(self.caixa / "ficha-v1.json") + ".sig").read_bytes(), sig)  # nada reassinado
        self.preparar(ficha(rede={"dominios": ["pypi.org"]}))  # a mesma v1, com outro conteúdo
        with self.assertRaises(TITULAR.Recusa) as ctx:
            self.assinar()
        self.assertIn("outro conteúdo", str(ctx.exception))

    def test_mesma_versao_com_assinatura_invalida_troca_so_o_sig(self):
        self.preparar()
        self.assertEqual(self.assinar()[0], 0)
        sig = Path(str(self.caixa / "ficha-v1.json") + ".sig")
        sig.write_bytes(b"assinatura estragada")
        self.assertEqual(self.assinar()[0], 0)
        self.assertTrue(K.aberturas.vigente(self.raiz, PROJETO, self.caixa, hoje=HOJE)["valida"])

    def test_versao_menor_que_a_maior_assinada_recusa(self):
        self.preparar(ficha(versao=2))
        self.assertEqual(self.assinar()[0], 0)
        self.preparar(ficha(versao=1))
        with self.assertRaises(TITULAR.Recusa) as ctx:
            self.assinar(versao=1)
        self.assertIn("menor que a maior", str(ctx.exception))

    def test_ancora_sem_fundacao_abertura_recusa_antes_da_senha(self):
        self.preparar()
        self.escrever_ancora("fundacao-decisao")
        self.recusa("atualize a âncora")
        self.assertEqual(self.perguntas, [])

    def test_chave_fora_da_ancora_recusa(self):
        self.preparar()
        self.recusa("não está na âncora", chave=self.chaves / "intruso")

    def test_ancora_ausente_recusa(self):
        self.preparar()
        with mock.patch.object(K.decisoes, "ANCORAS_PADRAO", (str(self.base / "nao-existe"),)):
            self.recusa("âncora ausente")

    def test_sem_ficha_preparada_ou_projeto_invalido(self):
        self.recusa("nenhuma ficha preparada")
        with self.assertRaises(TITULAR.Recusa):
            TITULAR.assinar_ficha(self.raiz, "../reversa-lab", confirmar=lambda _t: "x", hoje=HOJE)

    def test_assinatura_sem_o_ssh_agent(self):
        self.preparar()
        vistos = []
        real = TITULAR.subprocess.run

        def espiao(argv, **kw):
            vistos.append(kw.get("env") or {})
            return real(argv, **kw)
        with mock.patch.dict(os.environ, {"SSH_ASKPASS": "/bin/false", "SSH_ASKPASS_REQUIRE": "force"}), \
                mock.patch.object(TITULAR.subprocess, "run", side_effect=espiao):
            self.assertEqual(self.assinar()[0], 0)
        ambiente = vistos[0]
        self.assertTrue(ambiente["SSH_AUTH_SOCK"].endswith("sem-agente"))
        self.assertNotIn("SSH_ASKPASS", ambiente)
        self.assertNotIn("SSH_ASKPASS_REQUIRE", ambiente)

    def test_rascunho_por_vinculo_fisico_recusa(self):
        fora = self.base / "fora.json"
        fora.write_bytes(K.regras.canonico(ficha()))
        try:
            os.link(fora, self.rascunhos / "ficha-v1.json")
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"vínculo físico indisponível: {exc}")
        self.recusa("recusado")


class TestVerificarFichaEParser(TitularCase):
    def test_verificar_ficha(self):
        saida = io.StringIO()
        self.assertEqual(TITULAR.verificar_ficha(self.raiz, PROJETO, saida=saida, hoje=HOJE), 3)
        self.preparar()
        self.assertEqual(self.assinar()[0], 0)
        if os.name != "nt":  # no Linux, a que conta é a instalada na área do titular (o preparo do host a copia)
            self.instalar_na_area()
        saida = io.StringIO()
        self.assertEqual(TITULAR.verificar_ficha(self.raiz, PROJETO, saida=saida, hoje=HOJE), 0)
        res = json.loads(saida.getvalue())
        self.assertTrue(res["caixa_de_entrada"]["valida"])
        self.assertIn("canário", res["importante"])
        self.assertEqual(TITULAR.verificar_ficha(self.raiz, PROJETO, versao=1, saida=io.StringIO(), hoje=HOJE), 0)
        adulterada = K.regras.canonico(ficha(rede={"dominios": ["pypi.org"]}))
        for pasta in (self.caixa, self.area) if os.name != "nt" else (self.caixa,):
            (pasta / "ficha-v1.json").write_bytes(adulterada)
        self.assertEqual(TITULAR.verificar_ficha(self.raiz, PROJETO, saida=io.StringIO(), hoje=HOJE), 3)
        with self.assertRaises(TITULAR.Recusa):
            TITULAR.verificar_ficha(self.raiz, "../x", saida=io.StringIO())

    def test_parser_so_aceita_raiz_projeto_versao_e_chave(self):
        p = TITULAR.construir_parser()
        sub = next(a for a in p._actions if a.__class__.__name__ == "_SubParsersAction")
        opcoes = {nome: sorted(o for a in parser._actions for o in a.option_strings if o not in ("-h", "--help"))
                  for nome, parser in sub.choices.items()}
        # 1.7.10.1: o aceite de risco do canário (DECISAO-007) recebe também só o relatório do ensaio e a vigência.
        # 1.7.11, cópia cifrada lote 4: os três comandos da cópia recebem só caminhos, o hash do manifesto e a marca de
        # aceite sem âncora (nada de senha nem de argumento livre para o gpg; o N12 prova as recusas).
        self.assertEqual(opcoes, {"assinar-ficha": ["--chave", "--projeto", "--raiz", "--versao"],
                                  "verificar-ficha": ["--projeto", "--raiz", "--versao"],
                                  "aceitar-risco": ["--canario", "--chave", "--projeto", "--raiz", "--vigencia-ate"],
                                  "preparar-chave-copia": ["--casa", "--guardar-em", "--publica", "--raiz"],
                                  "conferir-copia": ["--casa", "--origem", "--raiz", "--sha256-manifesto"],
                                  "decifrar-copia": ["--aceitar-sem-ancora", "--casa", "--destino", "--origem", "--raiz",
                                                     "--sha256-manifesto"]})
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            p.parse_args(["assinar-ficha", "--raiz", "r", "--proj", "x"])  # sem abreviação

    @unittest.skipUnless(os.name == "posix", "a área do titular só existe no Linux")
    def test_no_linux_o_codigo_segue_a_ficha_instalada(self):
        """No Ubuntu vale a ficha da área do titular: caixa de entrada válida sem a instalada dá 3 (antes, dava 0)."""
        self.preparar()
        self.assertEqual(self.assinar()[0], 0)
        saida = io.StringIO()
        self.assertEqual(TITULAR.verificar_ficha(self.raiz, PROJETO, saida=saida, hoje=HOJE), 3)
        res = json.loads(saida.getvalue())
        self.assertEqual((res["caixa_de_entrada"]["valida"], res["area_do_titular"]["valida"]), (True, False))
        self.instalar_na_area()
        self.assertEqual(TITULAR.verificar_ficha(self.raiz, PROJETO, saida=io.StringIO(), hoje=HOJE), 0)
        Path(str(self.area / "ficha-v1.json") + ".sig").write_bytes(b"assinatura estragada")
        self.assertEqual(TITULAR.verificar_ficha(self.raiz, PROJETO, saida=io.StringIO(), hoje=HOJE), 3)

    def test_codigo_da_ferramenta_sem_print_e_sem_shell(self):
        texto = FERRAMENTA.read_text(encoding="utf-8")
        self.assertNotIn("shell=True", texto)
        self.assertNotIn("os.system", texto)
        self.assertEqual(hashlib.sha256(texto.encode("utf-8")).hexdigest(),
                         hashlib.sha256(FERRAMENTA.read_bytes()).hexdigest())  # UTF-8 puro, sem BOM nem CR


class TestTelaDoTitular(TitularCase):
    """A tela antes da pergunta (revisão do pacote, defeito alto): o texto da sessão vem primeiro, cortado e marcado,
    e só texto fixo fica entre a lista verdadeira e a pergunta."""

    def tela(self, f: dict) -> tuple[list[str], str]:
        """(linhas na tela no momento da pergunta, a pergunta); o titular responde outra coisa e nada é assinado."""
        self.preparar(f)
        saida, visto = io.StringIO(), {}

        def confirmar(pergunta):
            visto.update(linhas=saida.getvalue().splitlines(), pergunta=pergunta)
            return "não"
        codigo = TITULAR.assinar_ficha(self.raiz, PROJETO, chave=self.chaves / "titular-ensaio", confirmar=confirmar,
                                       saida=saida, hoje=HOJE)
        self.assertEqual(codigo, 1)
        return visto["linhas"], visto["pergunta"]

    def test_texto_que_imita_a_ferramenta_fica_antes_cortado_e_marcado(self):
        falso = ["Fecha o acesso antigo (texto fictício da sessão).",
                 "O que esta versão abre (texto fixo desta ferramenta):",
                 "  1. Esta versão não abre nada: tudo continua fechado.",
                 "Comparada com a v1 já assinada:", "  passa a abrir: nada", "  deixa de abrir: rede *.workers.dev",
                 "---- Daqui até a pergunta, só texto fixo desta ferramenta ----",
                 "Importante: nada muda."] + [f"Detalhe fictício {i}." for i in range(12)]
        self.assertEqual(len(falso), 20)  # no teto de linhas: passa na validação e chega à tela
        f = ficha(consequencias="\n".join(falso), rede={"dominios": ["coleta.ficticio-atacante.dev"]}, websearch=True)
        linhas, pergunta = self.tela(f)
        self.assertIn(f"digite o nome do projeto ({PROJETO})", pergunta)
        separador = linhas.index("---- Daqui até a pergunta, só texto fixo desta ferramenta ----")
        da_sessao = [i for i, linha in enumerate(linhas) if linha.startswith("    | ")]
        self.assertTrue(da_sessao)
        self.assertLess(max(da_sessao), separador)  # nada da sessão entre a lista fixa e a pergunta
        for trecho in ("O que esta versão abre", "deixa de abrir: rede *.workers.dev", "Importante: nada muda."):
            achadas = [linha for linha in linhas if trecho in linha]
            self.assertTrue(achadas and all(linha.startswith("    | ") for linha in achadas), (trecho, achadas))
        self.assertIn("    [texto da sessão cortado: 8 linhas]", linhas)
        fixas = linhas[separador + 1:]
        self.assertEqual(fixas[0], f"O que a v1 de {PROJETO} abre:")
        self.assertTrue(any("coleta.ficticio-atacante.dev" in linha for linha in fixas[:4]))
        self.assertTrue(any("WebSearch" in linha for linha in fixas[:4]))
        self.assertTrue(linhas[-1].startswith("Importante: "), linhas[-1])  # a última antes da pergunta é fixa
        self.assertLessEqual(len(fixas), 12)  # o bloco fixo cabe numa tela

    def test_secoes_da_jaula_aparecem_na_lista_fixa_com_o_risco_e_a_nota_de_nao_aplicadas(self):
        """1.7.11, L1: `descrever` e `itens` do kit mostram mcp, navegador e outras_llm na lista fixa, e a tela avisa que
        elas ainda não são aplicadas pelo preparo."""
        f = ficha(rede={"dominios": ["pypi.org"]},
                  mcp=[{"nome": "fsn", "origem": "conta", "conector": "Conector do escritorio",
                        "ferramentas": ["buscar_clientes", "get_processo"], "ocultar": ["salvar_nota"],
                        "conteudo_de_terceiros": True}],
                  navegador={"dominios": ["*.tjsp.jus.br", "esaj.tjsp.jus.br"], "logins": ["esaj.tjsp.jus.br"],
                             "modos": ["sessao", "login"]},
                  outras_llm=[{"provedor": "openai-codex", "autenticacao": "conta_chatgpt", "modos": ["exec"],
                               "conteudo_de_terceiros": True, "teto_chamadas_dia": 30,
                               "r55": {"plano": "Plus", "treinamento_desligado": True, "conferido_em": "2026-10-30"}}])
        linhas, _pergunta = self.tela(f)
        fixas = linhas[linhas.index("---- Daqui até a pergunta, só texto fixo desta ferramenta ----") + 1:]
        texto = " ".join(fixas)
        for trecho in ("CONSULTAR no conector 'Conector do escritorio'", "buscar_clientes", "inclusive de outros clientes",
                       "perfil novo só deste projeto",
                       "tjsp.jus.br e qualquer subdomínio de tjsp.jus.br", "Você poderá entrar (login) em esaj.tjsp.jus.br",
                       "conteúdo de clientes deste projeto, que vai à OpenAI (EUA)",
                       "passa a abrir: mcp fsn:buscar_clientes", "navegador-login esaj.tjsp.jus.br",
                       "outras_llm openai-codex:exec", "o navegador alcança estes sites; os comandos da sessão não",
                       "Para entrar em esaj.tjsp.jus.br, rode: abrir-navegador-", " login esaj.tjsp.jus.br",
                       "Nota: as seções mcp, navegador e outras_llm só passam a valer"):
            self.assertIn(trecho, texto)
        self.assertNotIn("salvar_nota", texto)  # o que fica oculto não aparece como aberto
        self.assertNotIn("GRAVAR", texto)  # só consulta: nenhum bloco de gravação
        self.assertFalse(any("FERRAMENTAS QUE GRAVAM" in linha for linha in linhas))
        self.assertTrue(linhas[-1].startswith("Importante: "), linhas[-1])
        # sem as seções, a nota não aparece
        linhas, _ = self.tela(ficha())
        self.assertFalse(any(linha.startswith("Nota: as seções mcp") for linha in linhas))

    def test_ferramentas_que_gravam_aparecem_em_separado_com_o_risco_antes_da_pergunta(self):
        """DECISAO-011: o conector do escritório com as ferramentas que gravam; a tela as mostra num bloco à parte, antes
        da comparação e da pergunta, com o risco em português simples, e a comparação separa o que passa a gravar."""
        f = ficha(mcp=[{"nome": "fsn", "origem": "conta", "conector": "Conector do escritorio",
                        "ferramentas": ["buscar_clientes", "get_processo", "salvar_nota", "propor_operacoes",
                                     "confirmar_operacoes", "escanear_vault"],
                        "ocultar": [], "conteudo_de_terceiros": True}])
        linhas, pergunta = self.tela(f)
        separador = linhas.index("---- Daqui até a pergunta, só texto fixo desta ferramenta ----")
        fixas = linhas[separador + 1:]
        titulo = next(i for i, linha in enumerate(fixas) if linha.startswith("ATENÇÃO, FERRAMENTAS QUE GRAVAM"))
        comparacao = next(i for i, linha in enumerate(fixas) if linha.startswith("Comparada com"))
        consulta = next(i for i, linha in enumerate(fixas) if "CONSULTAR no conector" in linha)
        self.assertLess(consulta, titulo)  # a consulta fica na lista numerada; as que gravam, depois e à parte
        self.assertLess(titulo, comparacao)
        self.assertRegex(fixas[consulta], r"^  [0-9]+\. ")  # numerada, como as outras aberturas
        bloco = " ".join(fixas[titulo:comparacao])
        for trecho in ("a sessão poderá criar, mudar e apagar dados do escritório", "GRAVAR no conector 'Conector do escritorio'",
                       "salvar_nota", "propor_operacoes", "confirmar_operacoes", "escanear_vault",
                       "texto malicioso numa página ou num documento", "sem pedir a sua confirmação"):
            self.assertIn(trecho, bloco)
        self.assertNotIn("buscar_clientes", bloco)  # as de consulta não entram no bloco das que gravam
        self.assertNotIn("salvar_nota", " ".join(fixas[:titulo]))
        for trecho in ("passa a abrir: ", "mcp fsn:buscar_clientes", "mcp-grava fsn:salvar_nota"):
            self.assertIn(trecho, " ".join(fixas[comparacao:]))
        self.assertIn(f"digite o nome do projeto ({PROJETO})", pergunta)
        self.assertTrue(linhas[-1].startswith("Importante: "), linhas[-1])

    def test_texto_com_linhas_vazias_em_excesso_recusa_antes_de_mostrar(self):
        self.preparar(ficha(consequencias="Texto." + "\n" * 60 + "O que esta versão abre (texto fixo desta ferramenta):"))
        self.recusa("consequencias")
        self.assertEqual(self.perguntas, [])

    def test_texto_da_sessao_em_faixas_sem_vazias_seguidas(self):
        """Revisão do pacote (31/10/2026): cada linha quebra em faixas de até 70 colunas, todas marcadas; a linha de
        300 'x' vira cinco faixas (não uma só truncada), e as faixas contam para o teto de 12."""
        linhas = TITULAR.texto_da_sessao("\n".join(["a", "", "", "b", "x" * 300] + [f"l{i}" for i in range(15)]))
        self.assertEqual(linhas[:4], ["    | a", "    | ", "    | b", "    | " + "x" * 70])
        self.assertEqual((len(linhas), linhas[-1]), (13, "    [texto da sessão cortado: 11 linhas]"))
        self.assertEqual(TITULAR.texto_da_sessao("\n\nsó isto"), ["    | só isto"])

    def test_faixa_de_200_caracteres_nao_passa_de_76_colunas(self):
        """Uma linha de 200 caracteres gera faixas que começam todas com '    | ' e nenhuma passa de 76 colunas (70
        de conteúdo + 6 da marca); caractere largo (CJK) conta 2 colunas."""
        def larg(s):
            return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)
        for linha in ("y" * 200, "漢" * 100):
            with self.subTest(linha=linha[:4]):
                faixas = TITULAR.texto_da_sessao(linha)
                self.assertTrue(faixas and all(f.startswith("    | ") for f in faixas), faixas)
                self.assertTrue(all(larg(f) <= 76 for f in faixas), [larg(f) for f in faixas])

    def test_fora_da_copia_protegida_avisa_antes_da_pergunta(self):
        self.assertFalse(TITULAR.conferir_copia()["protegida"])
        self.preparar()
        codigo, texto = self.assinar()
        self.assertEqual(codigo, 0, texto)
        aviso = texto.index("Atenção: esta cópia da ferramenta não está na área protegida")
        self.assertLess(aviso, texto.index("Importante: "))


class TestCaixaSemLigacao(TitularCase):
    def test_caixa_de_entrada_ligada_recusa_e_nada_vai_para_o_outro_lado(self):
        """A revisão pediu o teste negativo: caixa de entrada como junção (Windows) ou link (POSIX)."""
        self.preparar()
        fora = self.base / "fora"
        fora.mkdir()
        self.caixa.parent.mkdir(parents=True)
        criar_ligacao_dir(self.caixa, fora)
        with self.assertRaises(TITULAR.Recusa) as ctx:
            self.assinar()
        self.assertIn("ligação", str(ctx.exception))
        self.assertEqual(list(fora.iterdir()), [])
        self.assertEqual(self.perguntas, [])  # recusa antes de mostrar e de pedir a senha


class TestCopiaProtegida(TitularCase):
    """A cópia protegida da ferramenta (revisão do pacote, defeito médio): o SHA-256 dela e do kit contra o hashes.json
    da área, o dono e os direitos e o Python, antes de importar o kit."""

    def montar_copia(self, versao: str = "9.9.9"):
        # Pelo caminho real: a ferramenta calcula o AQUI com resolve(), e a pasta temporária do runner do Windows vem
        # com nome curto (RUNNER~1), que não seria "relativo" ao COPIA_PROTEGIDA do teste.
        base = Path(os.path.realpath(self.base)) / "protegida"
        raiz = base / versao
        (raiz / "assets" / "host").mkdir(parents=True)
        shutil.copyfile(FERRAMENTA, raiz / "assets" / "host" / "fundacao_titular.py")
        shutil.copytree(KIT / "fundacao", raiz / "assets" / "fundacao-kit" / "fundacao",
                        ignore=shutil.ignore_patterns("__pycache__"))
        arquivos = {p.relative_to(raiz).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(raiz.rglob("*")) if p.is_file()}
        python = Path(os.path.realpath(sys.executable))
        (raiz / "hashes.json").write_text(json.dumps(
            {"schema_version": TITULAR.ESQUEMA_HASHES, "versao": versao, "arquivos": arquivos,
             "python": {"caminho": str(python), "sha256": hashlib.sha256(python.read_bytes()).hexdigest()}}),
            encoding="utf-8")
        spec = importlib.util.spec_from_file_location("_titular_na_copia_protegida",
                                                      raiz / "assets" / "host" / "fundacao_titular.py")
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)  # só define funções: o kit da cópia não é importado aqui
        modulo.COPIA_PROTEGIDA = {"nt": str(base), "posix": str(base)}
        return raiz, modulo

    def recusa_da_copia(self, modulo, trecho: str, aqui=None) -> None:
        with self.assertRaises(modulo.Recusa) as ctx:
            modulo.conferir_copia(aqui)
        self.assertIn(trecho, str(ctx.exception))

    def test_caminhos_iguais_aos_do_kit(self):
        self.assertEqual(TITULAR.COPIA_PROTEGIDA, {"nt": K.aberturas.FERRAMENTA_WINDOWS,
                                                   "posix": K.aberturas.FERRAMENTA_POSIX})
        self.assertEqual(TITULAR.ESQUEMA_HASHES, K.aberturas.ESQUEMA_HASHES)
        self.assertEqual(SKILL.joinpath(*K.aberturas.REL_FERRAMENTA), FERRAMENTA)

    def test_confere_hashes_arquivos_e_python(self):
        raiz, modulo = self.montar_copia()
        with mock.patch.object(modulo, "_problemas_de_dono_posix", return_value=[]), \
                mock.patch.object(modulo, "_direitos_concedidos_windows", return_value=[]):
            self.assertEqual(modulo.conferir_copia(), {"protegida": True, "versao": "9.9.9", "raiz": str(raiz)})
            alvo = raiz / "assets" / "fundacao-kit" / "fundacao" / "core" / "aberturas_regras.py"
            original = alvo.read_bytes()
            alvo.write_bytes(original + b"\n# alterado na copia\n")
            self.recusa_da_copia(modulo, "não confere")
            alvo.write_bytes(original)
            extra = alvo.parent / "extra.py"
            extra.write_text("VALOR = 1\n", encoding="utf-8")
            self.recusa_da_copia(modulo, "não confere")
            extra.unlink()
            sombra = raiz / "assets" / "fundacao-kit" / "json"  # iria para o sys.path antes da biblioteca padrão
            sombra.mkdir()
            self.recusa_da_copia(modulo, "mais que a pasta fundacao")
            sombra.rmdir()
            self.recusa_da_copia(modulo, "fora da forma da cópia", aqui=raiz / "assets" / "outra")
            hashes = raiz / "hashes.json"
            dados = json.loads(hashes.read_text(encoding="utf-8"))
            hashes.write_text(json.dumps({**dados, "versao": "1.0.0"}), encoding="utf-8")
            self.recusa_da_copia(modulo, "fora da forma")
            if os.name == "nt":
                outro = {"caminho": str(raiz / "python.exe"), "sha256": "0" * 64}
                hashes.write_text(json.dumps({**dados, "python": outro}), encoding="utf-8")
                self.recusa_da_copia(modulo, "Python fixado")
            hashes.unlink()
            self.recusa_da_copia(modulo, "ausente")

    def test_copia_que_esta_conta_altera_recusa(self):
        """Sem trocar as sondas: a pasta temporária é desta conta, então a cópia não está protegida."""
        if os.name != "nt" and os.geteuid() == 0:
            self.skipTest("como root, a pasta temporária é de root")
        _raiz, modulo = self.montar_copia()
        self.recusa_da_copia(modulo, "pode ser alterada")

    def test_na_copia_protegida_a_ancora_precisa_estar_protegida(self):
        """Na cópia protegida, a âncora precisa estar protegida. No Windows a prova é em processo
        (_ancora_protegida_windows), SEM powershell/icacls pelo nome nu (regressão da revisão); no POSIX,
        decisoes.conferir_ancora, que lá não abre processo."""
        self.preparar()
        protegida = {"protegida": True, "versao": "9.9.9", "raiz": "x"}

        def com_ancora(desprotegida: bool):
            if os.name == "nt":
                achados = ["GENERIC_WRITE em " + str(self.ancora)] if desprotegida else []
                nao_chamar = mock.patch.object(K.decisoes, "conferir_ancora",
                                               side_effect=AssertionError("não pode rodar powershell/icacls no Windows"))
                probe = mock.patch.object(TITULAR, "_ancora_protegida_windows", return_value=achados)
                return nao_chamar, probe
            estado = {"protegida": not desprotegida, "motivo": "esta conta consegue: GENERIC_WRITE"}
            return (mock.patch.object(K.decisoes, "conferir_ancora", return_value=estado),)
        with mock.patch.object(TITULAR, "conferir_copia", return_value=protegida):
            for ctx in com_ancora(True):
                ctx.start()
                self.addCleanup(ctx.stop)
            self.recusa("não está protegida")
        self.assertEqual(self.perguntas, [])
        with mock.patch.object(TITULAR, "conferir_copia", return_value=protegida):
            for ctx in com_ancora(False):
                ctx.start()
                self.addCleanup(ctx.stop)
            codigo, texto = self.assinar()
        self.assertEqual(codigo, 0, texto)
        self.assertNotIn("Atenção:", texto)

    @unittest.skipUnless(os.name == "nt", "a regressão do powershell/icacls pelo nome nu é só no Windows")
    def test_assinar_na_copia_protegida_nao_roda_executavel_por_nome_nu(self):
        """Revisão do pacote (31/10/2026): toda a cerimônia só spawna executável por caminho absoluto do sistema (o
        ssh-keygen), nunca powershell.exe nem icacls pelo nome nu, que CreateProcess buscaria na pasta atual."""
        self.preparar()
        vistos, real = [], TITULAR.subprocess.run

        def espiao(argv, **kw):
            vistos.append(argv)
            return real(argv, **kw)
        protegida = {"protegida": True, "versao": "9.9.9", "raiz": "x"}
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NoDefaultCurrentDirectoryInExePath", None)  # como no PowerShell do titular
            with mock.patch.object(TITULAR, "conferir_copia", return_value=protegida), \
                    mock.patch.object(TITULAR, "_ancora_protegida_windows", return_value=[]), \
                    mock.patch.object(K.decisoes, "conferir_ancora",
                                      side_effect=AssertionError("não pode rodar powershell/icacls")), \
                    mock.patch.object(TITULAR.subprocess, "run", side_effect=espiao):
                self.assertEqual(self.assinar()[0], 0)
        sistema = os.path.join(os.environ["SystemRoot"], "System32").casefold()
        for argv in vistos:
            exe = (argv[0] if isinstance(argv, (list, tuple)) else argv)
            self.assertTrue(os.path.isabs(exe), f"executável pelo nome nu: {exe}")
            self.assertIn("ssh-keygen", os.path.basename(exe).casefold())
            self.assertTrue(os.path.realpath(exe).casefold().startswith(sistema), exe)


@unittest.skipUnless(os.name == "nt", "a prova da âncora em processo (CreateFileW e reparse) é a do Windows")
class TestAncoraNoWindowsSemMock(TitularCase):
    """Reconferência do pacote (01/11/2026): a prova da âncora no Windows (_ancora_protegida_windows) decide se o
    titular assina na cópia protegida, e os testes só a usavam simulada. Aqui ela roda contra arquivos reais de ENSAIO
    (a âncora numa pasta temporária, desta conta) e uma junção de verdade (mklink /J), sem processo filho."""

    def nenhum_processo(self):
        return mock.patch.object(TITULAR.subprocess, "run", side_effect=AssertionError("a prova abriu um processo"))

    def test_ancora_de_ensaio_desta_conta_da_os_direitos_de_escrita(self):
        with self.nenhum_processo():
            achados = TITULAR._ancora_protegida_windows(self.ancora)
        self.assertTrue(any(a.startswith("GENERIC_WRITE em ") and a.endswith(str(self.ancora)) for a in achados),
                        achados)
        self.assertTrue(any(a == f"ADD_FILE em {self.ancora.parent}" for a in achados), achados)
        self.assertFalse(any("ligação" in a for a in achados), achados)

    def test_juncao_no_caminho_da_ancora_aparece(self):
        ligada = self.base / "ancora-ligada"
        criar_ligacao_dir(ligada, self.ancora.parent)
        with self.nenhum_processo():
            achados = TITULAR._ancora_protegida_windows(ligada / self.ancora.name)
        self.assertIn(f"ligação no caminho da âncora: {ligada}", achados)

    def test_conferir_ancora_antes_recusa_a_ancora_desta_conta(self):
        with self.nenhum_processo(), \
                mock.patch.object(K.decisoes, "conferir_ancora", side_effect=AssertionError("powershell/icacls")):
            with self.assertRaises(TITULAR.Recusa) as ctx:
                TITULAR.conferir_ancora_antes(self.chaves / "titular-ensaio", self.ancora, K, exigir_protegida=True)
        self.assertIn("não está protegida", str(ctx.exception))
        self.assertIn("GENERIC_WRITE", str(ctx.exception))
        with self.nenhum_processo():  # fora da cópia protegida, a mesma âncora passa (a tela avisa da cópia)
            TITULAR.conferir_ancora_antes(self.chaves / "titular-ensaio", self.ancora, K, exigir_protegida=False)


class Tela(io.StringIO):
    """Um terminal de ensaio: isatty verdadeiro."""

    def isatty(self):
        return True


class TestJanelaDaCaixaExecutar(TitularCase):
    """Reconferência do pacote (01/11/2026): pela caixa Executar (Win+R), o console fecha quando a ferramenta termina e
    some o 'Assinada... gravada em', o 'Próximo passo' ou o 'Recusado'. Com terminal, main() espera um Enter depois
    do resultado; sem terminal (o teste de sempre, código 2), não espera."""

    def rodar_main(self, argv: list[str], respostas: list[str]) -> tuple[int, list, str, str]:
        entrada, saida, erro, vistos = Tela(), Tela(), Tela(), []

        def responder(pergunta=""):
            vistos.append((pergunta, saida.getvalue(), erro.getvalue()))
            return respostas.pop(0)
        with mock.patch.dict(os.environ, {}, clear=False), mock.patch.object(TITULAR.sys, "stdin", entrada), \
                mock.patch.object(TITULAR.sys, "stdout", saida), mock.patch.object(TITULAR.sys, "stderr", erro), \
                mock.patch("builtins.input", side_effect=responder):
            codigo = TITULAR.main(argv)
        return codigo, vistos, saida.getvalue(), erro.getvalue()

    def argv(self, *extra) -> list[str]:
        return ["assinar-ficha", "--raiz", str(self.raiz), "--projeto", PROJETO,
                "--chave", str(self.chaves / "titular-ensaio"), *extra]

    def test_espera_o_enter_depois_de_uma_recusa(self):
        codigo, vistos, _saida, erro = self.rodar_main(self.argv(), [""])  # nenhuma ficha preparada: Recusado
        self.assertEqual(codigo, 2)
        self.assertEqual(len(vistos), 1, vistos)
        pergunta, _antes_saida, antes_erro = vistos[0]
        self.assertIn("Tecle Enter", pergunta)
        self.assertIn("Recusado: nenhuma ficha preparada", antes_erro)  # o resultado já estava na tela

    def test_espera_o_enter_depois_de_assinar_e_de_cancelar(self):
        self.preparar()
        codigo, vistos, saida, _erro = self.rodar_main(self.argv(), [PROJETO, ""])
        self.assertEqual(codigo, 0, saida)
        self.assertEqual([p[0] for p in vistos][1:], ["\n" + TITULAR.ESPERA_FINAL])
        self.assertIn("Assinada pela chave de titular-ensaio", vistos[1][1])
        self.assertIn("Próximo passo", vistos[1][1])
        self.preparar(ficha(versao=2))
        codigo, vistos, saida, _erro = self.rodar_main(self.argv(), ["não", ""])
        self.assertEqual(codigo, 1)
        self.assertIn("Cancelado: nada foi assinado", vistos[-1][1])
        self.assertIn("Tecle Enter", vistos[-1][0])

    def test_espera_o_enter_depois_de_argumento_errado_e_de_erro_inesperado(self):
        codigo, vistos, _saida, erro = self.rodar_main(["assinar-ficha", "--raiz", str(self.raiz)], [""])
        self.assertEqual((codigo, len(vistos)), (2, 1))
        self.assertIn("--projeto", erro)
        with mock.patch.object(TITULAR, "assinar_ficha", side_effect=RuntimeError("falha de ensaio")):
            codigo, vistos, _saida, erro = self.rodar_main(self.argv(), [""])
        self.assertEqual((codigo, len(vistos)), (2, 1))
        self.assertIn("RuntimeError: falha de ensaio", vistos[0][2])  # o detalhe fica na tela até o Enter

    def test_sem_terminal_nao_espera(self):
        with mock.patch.object(TITULAR.sys.stdin, "isatty", return_value=False), \
                mock.patch.object(TITULAR.sys, "stderr", io.StringIO()), \
                mock.patch("builtins.input", side_effect=AssertionError("esperou o Enter sem terminal")):
            self.assertEqual(TITULAR.main(self.argv()), 2)
        with mock.patch.object(TITULAR.sys, "stdin", Tela()), mock.patch.object(TITULAR.sys, "stdout", io.StringIO()), \
                mock.patch.object(TITULAR.sys, "stderr", io.StringIO()), \
                mock.patch("builtins.input", side_effect=AssertionError("esperou o Enter com a saída redirecionada")):
            self.assertEqual(TITULAR.main(["verificar-ficha", "--raiz", str(self.raiz), "--projeto", PROJETO]), 3)


class TestAmbienteDoKeygen(TitularCase):
    """Reconferência do pacote (01/11/2026): o ssh-keygen recebia o ambiente do titular, que uma sessão pode ter
    plantado (no Windows, em HKCU\\Environment): SSH_SK_PROVIDER e SSH_SK_HELPER escolhem o que roda numa chave sk-*.
    Agora vai só o ambiente mínimo, e a assinatura (real, com a chave de ensaio) continua funcionando."""

    def test_so_o_ambiente_minimo_chega_ao_ssh_keygen(self):
        self.preparar()
        plantadas = {"SSH_SK_PROVIDER": str(self.base / "provedor-plantado"), "SSH_SK_HELPER": str(self.base / "x"),
                     "SSH_ASKPASS": str(self.base / "y"), "SSH_ASKPASS_REQUIRE": "force", "PYTHONPATH": str(self.base),
                     "PATH": str(self.base) + os.pathsep + os.environ["PATH"]}
        vistos, real = [], TITULAR.subprocess.run

        def espiao(argv, **kw):
            if list(argv[1:3]) == ["-Y", "sign"]:  # o -Y verify depois é o do kit (decisoes.verificar_assinatura)
                vistos.append(dict(kw.get("env") or {}))
            return real(argv, **kw)
        with mock.patch.dict(os.environ, plantadas), mock.patch.object(TITULAR.subprocess, "run", side_effect=espiao):
            codigo, texto = self.assinar()
        self.assertEqual(codigo, 0, texto)
        self.assertEqual(len(vistos), 1)
        ambiente = vistos[0]
        for nome in plantadas:
            if nome != "PATH":
                self.assertNotIn(nome, ambiente)
        self.assertNotIn(str(self.base), ambiente["PATH"])
        self.assertTrue(ambiente["SSH_AUTH_SOCK"].endswith("sem-agente"))
        permitidas = set(TITULAR.AMBIENTE_DO_KEYGEN["nt" if os.name == "nt" else "posix"]) | {"PATH", "SSH_AUTH_SOCK"}
        self.assertEqual(set(ambiente) - permitidas, set())


if __name__ == "__main__":
    unittest.main()
