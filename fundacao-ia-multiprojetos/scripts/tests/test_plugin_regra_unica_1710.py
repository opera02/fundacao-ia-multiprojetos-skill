"""plugin_candidato.py e o kit: uma receita só para o manifesto e uma regra só para o plugin (1.7.10; integração, itens
I4 e I12; emendas E3 e E4 dos contratos do lote 2).

- I4 (E3): o `manifesto_sha256` do plugin_candidato (manifesto, conferir, revisar, a linha pronta da ficha e o montar)
  é o `aberturas_plugins.sha256_do_manifesto` do kit sobre `{caminho, bytes, sha256}`: igual, sobre a mesma pasta, ao
  `conferir_pasta_do_plugin` e ao `conferir_plugin` do kit, que o `abertura preparar`, a ferramenta do titular e o
  preparo do host chamam. Antes, o JSON canônico com `schema_version`, `nome` e `tamanho` dava outro valor.
- I12 (E4): a ferramenta da sessão nunca é mais frouxa que o kit. Implicação, sobre um conjunto de candidatos: conforme
  no plugin_candidato => sem erro no `conferir_pasta_do_plugin` e a linha da ficha aceita pelo validador da ficha. As
  diferenças que a reconferência do ABERTURAS achou (.txt, .json, .yaml, .csv e imagens em skills/, NOTICE e COPYING na
  raiz) e as outras da comparação (chaves do cabeçalho, nome do plugin, tetos, bit de execução, '---' com NBSP, chave
  com espaço antes do ':') recusam pela regra daqui; o resto da leitura do cabeçalho, pela regra do kit por último.
- I17 (a implicação completa, segunda rodada): também os casos da sondagem da fase 1 do DOCS (context e agent no
  comando; etiqueta `!!str`, âncora `&a` e alias `*a` num valor; hooks ou mcpServers num valor ou numa chave recuada;
  cabeçalho num Markdown de apoio): o plugin_candidato os recusa pela regra do kit, por último.
- I16 (o caminho confiável): o allowed-tools, a menção '@' para fora, nome forte e pasta de segredo e o nome fora do
  UTF-8 recusam nos dois, cada um pela própria regra (o kit sozinho, antes, os aceitava; o nome fora do UTF-8 levantava
  UnicodeEncodeError). As funções de allowed-tools e da menção são as do kit (core/aberturas_markdown.py), a mesma
  regra nos dois. E8: o BOM só no começo, nos dois. Revisão da integração, rodada 2: também a menção para fora dentro
  de um trecho entre aspas e o '..' no fim do especificador (o teste diferencial contra a leitura do Claude Code
  2.1.302 fica no kit, test_aberturas_plugins_i16.TestLeituraDoClaudeCode). Reconferência da integração, rodada 2: o
  nome com caractere da área privada do Unicode (a face do Windows de um nome que o DrvFs mostra no Ubuntu com
  controle ou " * : < > ? \\ |) e o '$' em qualquer ponto da menção e do especificador, nos dois; no Linux, também a
  face do Ubuntu e a pasta terminada em ponto ou espaço.

O kit é o desta skill (assets/fundacao-kit), carregado pelo caminho, como o test_aberturas_fluxo.py faz. Pastas
descartáveis com dados fictícios; nada do candidato é executado.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from apoio import ENV, KIT, SCRIPTS
from test_plugin_candidato import AGENTE_OK, COMANDO_OK, MOD, SKILL_OK, Fundacao, escrever
from test_plugin_candidato_regras import GIF, JPG, PNG, WEBP, skill

if str(KIT) not in sys.path:  # o kit desta skill, pelo caminho (o mesmo que a ferramenta do titular carrega)
    sys.path.insert(0, str(KIT))
from fundacao.core import aberturas_markdown as markdown  # noqa: E402
from fundacao.core import aberturas_plugins as plugins  # noqa: E402
from fundacao.core import aberturas_regras as regras  # noqa: E402

MARCA_DO_KIT = "(regra do kit, aberturas_plugins.conferir_pasta_do_plugin)"
NBSP = "\N{NO-BREAK SPACE}"

# Aceitos pelos dois lados: {nome do candidato: (arquivos a mais, arquivos a tirar)}.
SKILL_COMPLETA = skill("name: ola\ndescription: Todas as chaves aceitas (fictícia).\nlicense: MIT\n"
                       "compatibility: qualquer\nmetadata:\n  autor: ficticio\nallowed-tools: Read, Grep\n"
                       "argument-hint: <tema>\ndisable-model-invocation: false\nuser-invocable: true\nmodel: sonnet\n"
                       "effort: low\npaths:\n  - docs/**\nwhen_to_use: quando pedirem um olá")
COMANDO_COMPLETO = skill("description: Resume (fictício).\nlicense: MIT\ncompatibility: qualquer\nmetadata:\n  a: b\n"
                         "allowed-tools: Read\nargument-hint: <arquivo>\ndisable-model-invocation: true\n"
                         "user-invocable: true\nmodel: haiku\neffort: low\nwhen_to_use: ao resumir")
AGENTE_COMPLETO = skill("name: revisor\ndescription: Revisa (fictício).\ntools: Read, Grep\ndisallowedTools: Write\n"
                        "model: inherit\ncolor: blue\neffort: low\nmaxTurns: 5")
ACEITOS = {
    "demo-base": ({}, ()),
    "demo-licencas": ({"LICENSE.md": "Licença fictícia.\n", "LICENSE.txt": "Licença fictícia.\n",
                       "skills/ola/LICENSE.md": "Licença da skill (fictícia).\n"}, ()),
    "demo-fundo": ({"skills/ola/a/b/c/d.md": "Apoio fundo.\n", "skills/ola/referências/índice.md": "Acentos.\n"}, ()),
    "demo-crlf": ({"skills/ola/SKILL.md": SKILL_OK.replace("\n", "\r\n"),
                   "commands/resumo.md": COMANDO_OK.replace("\n", "\r\n")}, ()),
    "demo-chaves": ({"skills/ola/SKILL.md": SKILL_COMPLETA, "commands/resumo.md": COMANDO_COMPLETO,
                     "agents/revisor.md": AGENTE_COMPLETO}, ()),
    "demo-autor": ({".claude-plugin/plugin.json": json.dumps({"name": "demo-autor", "description": "X.",
                                                              "version": "0.1.0", "author": {"name": "Autor"}})}, ()),
    "demo-fecho": ({"skills/ola/SKILL.md": "---\nname: ola\ndescription: Fecha com tab.\n--- \t\n\nCorpo.\n"}, ()),
    "demo-sem-licenca": ({}, ("LICENSE",)),
    # Itens I16 e E8: o que as regras novas do kit deixam passar, nos dois.
    "demo-bom": ({"skills/ola/SKILL.md": "\ufeff" + SKILL_OK, "commands/resumo.md": "\ufeff" + COMANDO_OK}, ()),
    "demo-especificador": ({"skills/ola/SKILL.md": skill("name: ola\ndescription: X.\nallowed-tools: Read(./docs/**), "
                                                         "Grep(casos/**)")}, ()),
    "demo-mencoes-de-dentro": ({"commands/resumo.md": skill("description: X.", 'Leia @docs/guia.md, @"a b.md" e '
                                                            "@./c.md; escreva a contato" + "@" + "exemplo.com.br.\n")},
                               ()),
    "demo-nome-fraco": ({"skills/ola/token-guia.md": "Nome fraco: só marcado na revisão.\n"}, ()),
}
# Recusados pela regra daqui (e pelo kit): o que o plugin_candidato aceitava antes da integração.
RECUSADOS_AQUI = {
    "demo-txt": {"skills/ola/notas.txt": "Notas.\n"},
    "demo-json": {"skills/ola/dados/x.json": '{"a": 1}\n'},
    "demo-yaml": {"skills/ola/dados/y.yaml": "a: 1\n"},
    "demo-yml": {"skills/ola/dados/z.yml": "b: 2\n"},
    "demo-csv": {"skills/ola/dados/t.csv": "a,b\n1,2\n"},
    "demo-png": {"skills/ola/imagens/a.png": PNG},
    "demo-jpg": {"skills/ola/imagens/b.jpg": JPG},
    "demo-jpeg": {"skills/ola/imagens/c.jpeg": JPG},
    "demo-gif": {"skills/ola/imagens/d.gif": GIF},
    "demo-webp": {"skills/ola/imagens/e.webp": WEBP},
    "demo-notice": {"NOTICE": "Aviso fictício.\n"},
    "demo-copying": {"COPYING": "Cópia fictícia.\n"},
    "demo-notice-md": {"NOTICE.md": "Aviso fictício.\n"},
    "demo-copying-txt": {"COPYING.txt": "Cópia fictícia.\n"},
    "demo-licence": {"LICENCE": "Licença fictícia.\n"},
    "demo-license-mit": {"LICENSE-MIT": "Licença fictícia.\n"},
    "demo-licenca-na-skill": {"skills/ola/LICENSE": "Licença fictícia.\n"},
    "demo-notice-na-skill": {"skills/ola/NOTICE": "Aviso fictício.\n"},
    "demo-skill-version": {"skills/ola/SKILL.md": skill("name: ola\ndescription: X.\nversion: 1.0")},
    "demo-skill-context": {"skills/ola/SKILL.md": skill("name: ola\ndescription: X.\ncontext: fork")},
    "demo-skill-agent": {"skills/ola/SKILL.md": skill("name: ola\ndescription: X.\nagent: Explore")},
    "demo-comando-name": {"commands/resumo.md": skill("name: resumo\ndescription: X.")},
    "demo-comando-paths": {"commands/resumo.md": skill("description: X.\npaths:\n  - src/**")},
    "demo-comando-version": {"commands/resumo.md": skill("description: X.\nversion: 1")},
    "demo-comando-context": {"commands/resumo.md": skill("description: X.\ncontext: fork")},  # item I17
    "demo-comando-agent": {"commands/resumo.md": skill("description: X.\nagent: Explore")},  # item I17
    "demo-agente-skills": {"agents/revisor.md": skill("name: revisor\ndescription: X.\nskills:\n  - ola")},
    "demo-chave-com-espaco": {"skills/ola/SKILL.md": skill("name : ola\ndescription: X.")},
    "demo-fecho-nbsp": {"skills/ola/SKILL.md": f"---\nname: ola\ndescription: X.\n---{NBSP}\nhooks: x\n---\nCorpo.\n"},
    "demo-abertura-nbsp": {"skills/ola/SKILL.md": f"---{NBSP}\nname: ola\ndescription: X.\n---\nCorpo.\n"},
}
# Recusados (aqui pela regra do kit, por último): o resto da leitura do cabeçalho.
RECUSADOS_NO_KIT = {
    "demo-hooks-no-valor": {"skills/ola/SKILL.md": skill("name: ola\ndescription: Usa hooks do git (fictício).")},
    "demo-ancora": {"skills/ola/SKILL.md": skill("name: ola\ndescription: X.\nmetadata:\n  a: &ancora 1")},
    "demo-barra": {"skills/ola/SKILL.md": skill("name: ola\ndescription: barra \\ invertida")},
    "demo-apelido": {"skills/ola/SKILL.md": skill("name: ola\ndescription: X, *apelido")},
    "demo-item-na-coluna": {"skills/ola/SKILL.md": skill("name: ola\ndescription: X.\nallowed-tools:\n- Read")},
    "demo-mesclagem": {"skills/ola/SKILL.md": skill("name: ola\ndescription: X.\n# <<: comentário")},
    "demo-mcp-comentado": {"agents/revisor.md": skill("name: revisor\ndescription: X.\ntools: Read\n# mcpServers: x")},
    "demo-cabecalho-no-apoio": {"skills/ola/referencias/guia.md": "---\ntitle: Guia\n---\nTexto.\n"},
    # Item I17: a sondagem da fase 1 do DOCS (a sessão aceitava pelas regras daqui; o kit recusa).
    "demo-etiqueta": {"skills/ola/SKILL.md": skill("name: ola\ndescription: !!str X.")},
    "demo-ancora-no-valor": {"skills/ola/SKILL.md": skill("name: ola\ndescription: &a X.")},
    "demo-alias-no-valor": {"skills/ola/SKILL.md": skill("name: ola\ndescription: *a")},
    "demo-mcp-no-valor": {"commands/resumo.md": skill("description: Explica mcpServers (fictício).")},
    "demo-hooks-recuado": {"skills/ola/SKILL.md": skill("name: ola\ndescription: X.\nmetadata:\n  hooks: x")},
    "demo-mcp-recuado": {"commands/resumo.md": skill("description: X.\nmetadata:\n  mcpServers: x")},
    "demo-apoio-com-hooks": {"skills/ola/referencias/guia.md": "---\ndescription: Guia.\nhooks: x\n---\nTexto.\n"},
}
# Item I16: recusados pela regra daqui E, sozinho, pelo kit (antes o kit os aceitava): {nome: (arquivos a mais, o
# caminho do motivo nos dois)}. As funções de allowed-tools e da menção são as do kit nos dois lados.
RECUSADOS_NOS_DOIS = {
    "demo-at-bash": ({"skills/ola/SKILL.md": skill("name: ola\ndescription: X.\nallowed-tools: Bash(curl:*)")},
                     "skills/ola/SKILL.md"),
    "demo-at-powershell": ({"commands/resumo.md": skill("description: X.\nallowed-tools: PowerShell")},
                           "commands/resumo.md"),
    "demo-at-monitor": ({"skills/ola/SKILL.md": skill("name: ola\ndescription: X.\nallowed-tools: Read, Monitor")},
                        "skills/ola/SKILL.md"),
    "demo-at-webfetch": ({"commands/resumo.md": skill("description: X.\nallowed-tools: WebFetch(domain:x.com.br)")},
                         "commands/resumo.md"),
    "demo-at-websearch": ({"skills/ola/SKILL.md": skill("name: ola\ndescription: X.\nallowed-tools: WebSearch")},
                          "skills/ola/SKILL.md"),
    "demo-at-mcp": ({"skills/ola/SKILL.md": skill("name: ola\ndescription: X.\nallowed-tools: mcp__x__y")},
                    "skills/ola/SKILL.md"),
    "demo-at-fora-da-lista": ({"skills/ola/SKILL.md": skill("name: ola\ndescription: X.\nallowed-tools: CronCreate")},
                              "skills/ola/SKILL.md"),
    "demo-at-formato": ({"skills/ola/SKILL.md": skill("name: ola\ndescription: X.\nallowed-tools: Read # Bash")},
                        "skills/ola/SKILL.md"),
    "demo-at-caminho": ({"skills/ola/SKILL.md": skill("name: ola\ndescription: X.\nallowed-tools: Edit(~/.bashrc)")},
                        "skills/ola/SKILL.md"),
    "demo-mencao-ssh": ({"commands/resumo.md": skill("description: X.", "Leia @~/.ssh/id_ed25519.\n")},
                        "commands/resumo.md"),
    "demo-mencao-passwd": ({"skills/ola/SKILL.md": SKILL_OK + "Veja @/etc/passwd.\n"}, "skills/ola/SKILL.md"),
    "demo-mencao-aspas": ({"commands/resumo.md": skill("description: X.", 'Leia @"x\n/../../outro/x.md" agora.\n')},
                          "commands/resumo.md"),
    "demo-mencao-virgula": ({"commands/resumo.md": skill("description: X.", "Leia @x,/../../outro/data/s.md\n")},
                            "commands/resumo.md"),
    "demo-id-rsa": ({"skills/ola/id_rsa.md": "chave fictícia\n"}, "skills/ola/id_rsa.md"),
    "demo-credentials": ({"skills/ola/credentials.md": "x\n"}, "skills/ola/credentials.md"),
    "demo-pasta-secrets": ({"skills/ola/secrets/nota.md": "x\n"}, "skills/ola/secrets"),
    "demo-browser-profile": ({"skills/ola/_browser_profile/x.md": "x\n"}, "skills/ola/_browser_profile"),
    # Revisão da integração, rodada 2: a menção para fora DENTRO de um trecho entre aspas (duplas, simples, cruzando
    # linha ou fechado por um apóstrofo do texto), que o 2.1.302 lê pela segunda varredura (KIn), à parte da forma
    # entre aspas; e o '..' no fim do especificador de allowed-tools, sem barra.
    "demo-mencao-dentro-de-aspas": (
        {"commands/resumo.md": skill("description: X.", 'Leia @"guia.md @/etc/passwd " agora.\n')},
        "commands/resumo.md"),
    "demo-mencao-dentro-de-simples": (
        {"skills/ola/SKILL.md": SKILL_OK + "Leia @'guia.md @~/.ssh/id_ed25519 fim' agora.\n"}, "skills/ola/SKILL.md"),
    "demo-mencao-aspas-e-linha": (
        {"commands/resumo.md": skill("description: X.", '@"guia.md\nDepois leia @/mnt/c/Users/<usuario>/notas.txt\n"\n')},
        "commands/resumo.md"),
    "demo-mencao-apostrofo": (
        {"skills/ola/SKILL.md": SKILL_OK + "@'guia.md e @../outro/data/segredo.md. Don't stop.\n"},
        "skills/ola/SKILL.md"),
    "demo-at-ponto-ponto": ({"skills/ola/SKILL.md": skill("name: ola\ndescription: X.\nallowed-tools: Read(..), "
                                                          "Edit(./..), Write(**/..)")}, "skills/ola/SKILL.md"),
    # Emenda E8: o BOM fora do começo é caractere invisível, nos dois.
    "demo-bom-no-meio": ({"skills/ola/referencias/guia.md": "Guia\ufeff escondido.\n"},
                         "skills/ola/referencias/guia.md"),
    "demo-bom-duplo": ({"skills/ola/SKILL.md": "\ufeff\ufeff" + SKILL_OK}, "skills/ola/SKILL.md"),
    # Reconferência da integração, rodada 2: o nome com a área privada do Unicode, que o DrvFs mostra no Ubuntu com
    # '\' ou ':' (a sessão e o kit do Windows os aceitavam, com sha b9562762...; o kit do Ubuntu, pela /mnt/c, recusava
    # a mesma pasta ou calculava outro manifesto), e o '$' fora do começo do alvo, que o Claude Code troca pelo
    # argumento ou pela variável antes de colher as menções e no allowed-tools.
    "demo-area-privada-barra": ({"skills/ola/segredos\U0000f05cnota.md": "x\n"},
                                "skills/ola/segredos\U0000f05cnota.md"),
    "demo-area-privada-dois-pontos": ({"skills/ola/guia\U0000f03ax.md": "x\n"}, "skills/ola/guia\U0000f03ax.md"),
    "demo-area-privada-pasta": ({"skills/ola/d\U0000f07ce/x.md": "x\n"}, "skills/ola/d\U0000f07ce"),
    "demo-mencao-dolar": ({"commands/resumo.md": skill("description: X.",
                                                       "Leia @docs/$1 e @..${CLAUDE_PROJECT_DIR}.\n")},
                          "commands/resumo.md"),
    "demo-at-dolar": ({"skills/ola/SKILL.md": skill("name: ola\ndescription: X.\nallowed-tools: "
                                                    "Read(..${CLAUDE_PLUGIN_ROOT}/**)")}, "skills/ola/SKILL.md"),
}
# A face do Ubuntu dos nomes que o DrvFs troca, e a pasta terminada em ponto ou espaço, que o Windows não abre pelo nome
# (reconferência da integração, rodada 2): só no Linux, que os guarda. {caminho: o do motivo nos dois}.
FACE_DO_UBUNTU = {"skills/ola/guia:x.md": "skills/ola/guia:x.md", "skills/ola/a\tb.md": "skills/ola/a\tb.md",
                  "skills/ola/q?.md": "skills/ola/q?.md", "skills/ola/a|b.md": "skills/ola/a|b.md",
                  "skills/ola/a\\b.md": "skills/ola/a\\b.md", "skills/ola/pasta./x.md": "skills/ola/pasta.",
                  "skills/ola/pasta /x.md": "skills/ola/pasta "}


def linha_da_ficha(texto: str) -> dict:
    """A linha pronta da ficha no REVISAO.md (caixa de aceite do titular)."""
    achado = re.search(r"Aceito listar na ficha de aberturas: `(\{.*\})`", texto)
    if achado is None:
        raise AssertionError("o REVISAO.md não traz a linha pronta da ficha")
    return json.loads(achado.group(1))


def ficha_com(item: dict) -> dict:
    """Uma ficha fictícia mínima do projeto demo com o plugin `item` (o resto dos tetos fixos passa)."""
    return {"schema_version": regras.SCHEMA, "ficha_id": "aberturas-demo", "project_id": "demo", "versao": 1,
            "motivo": "Teste fictício da integração.", "consequencias": "Nenhuma (ensaio).", "plugins": [item]}


class Base(Fundacao):
    def item(self, pasta: Path, sha: str | None) -> dict:
        return {"nome": pasta.name, "origem": f"plugins-candidatos/{pasta.name}", "manifesto_sha256": sha}

    def dos_dois_lados(self, pasta: Path) -> tuple[dict, dict]:
        return MOD.conferir(pasta), plugins.conferir_pasta_do_plugin(pasta, pasta.name)

    def implicacao(self, pasta: Path) -> tuple[dict, dict]:
        """Conforme aqui => sem erro no kit, o mesmo manifesto_sha256 e a linha da ficha aceita (item I12)."""
        pc, kit = self.dos_dois_lados(pasta)
        if pc["conforme"]:
            self.assertEqual(kit["erros"], [], f"{pasta.name}: conforme aqui e recusado no kit")
            self.assertEqual(pc["manifesto_sha256"], kit["manifesto_sha256"])
            item = self.item(pasta, pc["manifesto_sha256"])
            self.assertEqual(regras.validar(ficha_com(item), projeto="demo")["erros"], [], pasta.name)
            self.assertEqual(plugins.conferir_plugin(self.proj, item)["erros"], [], pasta.name)
        return pc, kit


class TestReceitaUnica(Base, unittest.TestCase):
    """Item I4 (emenda E3): o mesmo manifesto_sha256 em todas as pontas, sobre a mesma pasta."""

    def test_o_mesmo_manifesto_sha256_no_plugin_candidato_e_no_kit(self):
        pasta = self.candidato({"skills/ola/referências/índice.md": "Acentos no caminho.\n"})
        dados, sha = MOD.manifesto(pasta)
        kit = plugins.conferir_pasta_do_plugin(pasta)
        self.assertEqual(kit["erros"], [])
        self.assertEqual(sha, kit["manifesto_sha256"])  # plugin_candidato.manifesto(p)[1] == o do kit
        self.assertEqual(sha, plugins.conferir_pasta_do_plugin(pasta, "demo-kit")["manifesto_sha256"])
        self.assertEqual(dados["arquivos"], kit["arquivos"], "a lista mostrada é a do hash: {caminho, bytes, sha256}")
        self.assertEqual(sha, plugins.sha256_do_manifesto(dados["arquivos"]))
        ponta = plugins.conferir_plugin(self.proj, self.item(pasta, sha))  # a chamada do abertura preparar e do host
        self.assertEqual((ponta["erros"], ponta["manifesto_sha256"]), ([], sha))
        res = MOD.conferir(pasta)
        self.assertTrue(res["conforme"], res["motivos"])
        self.assertEqual((res["manifesto"], res["manifesto_sha256"]), (dados, sha))
        texto, revisado = MOD.revisar(pasta)
        self.assertEqual(revisado["manifesto_sha256"], sha)
        self.assertEqual(linha_da_ficha(texto), self.item(pasta, sha))
        # Contraprova: a receita de antes (o manifesto inteiro, com schema_version, nome e tamanho) dá outro valor.
        antes = {"schema_version": dados["schema_version"], "nome": dados["nome"],
                 "arquivos": [{"caminho": a["caminho"], "tamanho": a["bytes"], "sha256": a["sha256"]}
                              for a in dados["arquivos"]]}
        antigo = hashlib.sha256(json.dumps(antes, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                                .encode("utf-8")).hexdigest()
        self.assertNotEqual(antigo, sha)

    def test_as_tres_pontas_num_teste_so_sobre_a_mesma_pasta(self):
        """O I4 da folha ao pé da letra (revisão da integração, "faltou"): sobre a mesma pasta,
        plugin_candidato.manifesto(p)[1] == aberturas_plugins.conferir_pasta_do_plugin(p)["manifesto_sha256"] == o hash
        que o instalador do HOST calcula (preparo_host.conferir_plugin_da_ficha, com o kit da cópia da skill carregado
        sob nome próprio). Antes eram dois testes (I4 e I5), presos pela mesma função do kit."""
        from test_host_projeto_apoio import carregar_preparo
        pasta = self.candidato({"skills/ola/referências/índice.md": "Acentos no caminho.\n",
                                "skills/ola/referencias/crlf.md": "Linha um.\r\nLinha dois.\r\n"})
        da_sessao = MOD.manifesto(pasta)[1]
        do_kit = plugins.conferir_pasta_do_plugin(pasta)
        host = carregar_preparo()
        do_host = host.conferir_plugin_da_ficha(self.proj, self.item(pasta, ""))  # o instalador calcula, sem a ficha
        self.assertEqual((do_kit["erros"], do_host["erros"]), ([], []))
        self.assertRegex(da_sessao, r"^[0-9a-f]{64}$")
        self.assertEqual(da_sessao, do_kit["manifesto_sha256"])
        self.assertEqual(do_kit["manifesto_sha256"], do_host["manifesto_sha256"])
        conferido = host.conferir_plugin_da_ficha(self.proj, self.item(pasta, da_sessao))  # e confere o da ficha
        self.assertEqual((conferido["erros"], conferido["manifesto_sha256"]), ([], da_sessao))
        with open(pasta / "commands" / "resumo.md", "ab") as arq:  # um byte a mais muda as três juntas
            arq.write(b"x")
        depois = {MOD.manifesto(pasta)[1], plugins.conferir_pasta_do_plugin(pasta)["manifesto_sha256"],
                  host.conferir_plugin_da_ficha(self.proj, self.item(pasta, ""))["manifesto_sha256"]}
        self.assertEqual(len(depois), 1, depois)
        self.assertNotIn(da_sessao, depois)

    def test_montar_da_o_hash_e_a_linha_da_ficha_que_o_kit_aceita(self):
        origem = self.proj / "importado" / ".claude"
        escrever(origem, {"skills/ola/SKILL.md": SKILL_OK, "agents/revisor.md": AGENTE_OK,
                          "commands/resumo.md": COMANDO_OK})
        res = MOD.montar(self.raiz, "demo", "kit", origem)
        destino = Path(res["candidato"])
        self.assertEqual(res["manifesto_sha256"], plugins.conferir_pasta_do_plugin(destino)["manifesto_sha256"])
        self.assertEqual(res["ficha"], self.item(destino, res["manifesto_sha256"]))
        self.assertEqual(regras.validar(ficha_com(res["ficha"]), projeto="demo")["erros"], [])
        self.assertEqual(plugins.conferir_plugin(self.proj, res["ficha"])["erros"], [])

    def test_copia_instalada_com_o_mesmo_nome_da_o_mesmo_hash(self):
        # O preparo do host instala em /etc/fundacao-ia/projetos/<p>/plugins/<nome>/ e confere de novo pelo kit.
        pasta = self.candidato()
        instalada = self.base / "area-do-titular" / "plugins" / pasta.name
        shutil.copytree(pasta, instalada)
        sha = MOD.manifesto(pasta)[1]
        self.assertEqual(MOD.manifesto(instalada)[1], sha)
        self.assertEqual(plugins.conferir_pasta_do_plugin(instalada, pasta.name)["manifesto_sha256"], sha)
        self.assertEqual(MOD.conferir(instalada, projeto="demo")["manifesto_sha256"], sha)


class TestImplicacao(Base, unittest.TestCase):
    """Item I12 (emenda E4): conforme no plugin_candidato => sem erro no kit, sobre um conjunto de candidatos."""

    def test_conforme_aqui_implica_sem_erro_no_kit(self):
        conformes = 0
        for nome, (extras, sem) in ACEITOS.items():
            with self.subTest(aceito=nome):
                pc, _kit = self.implicacao(self.candidato(extras, nome=nome, sem=sem))
                self.assertTrue(pc["conforme"], pc["motivos"])
                conformes += 1
        nos_dois = {nome: extras for nome, (extras, _rel) in RECUSADOS_NOS_DOIS.items()}  # itens I16 e E8
        for nome, extras in {**RECUSADOS_AQUI, **RECUSADOS_NO_KIT, **nos_dois}.items():
            with self.subTest(recusado=nome):
                pc, kit = self.implicacao(self.candidato(extras, nome=nome))
                self.assertFalse(pc["conforme"], f"{nome}: devia recusar")
                self.assertTrue(kit["erros"], f"{nome}: o caso tem de ser uma recusa do kit")
        self.assertEqual(conformes, len(ACEITOS), "a implicação não pode valer só por vazio")

    def test_as_diferencas_achadas_recusam_pela_regra_daqui(self):
        # Não basta a conferência final do kit: a lista daqui fica dentro da dele (a folha: "alinhar a lista").
        for nome, extras in RECUSADOS_AQUI.items():
            with self.subTest(nome=nome):
                pc = MOD.conferir(self.candidato(extras, nome=nome))
                self.assertFalse(pc["conforme"])
                rel = next(iter(extras))
                proprios = [m for m in pc["motivos"] if not m.endswith(MARCA_DO_KIT)]
                self.assertTrue(any(m.startswith(rel) for m in proprios), pc["motivos"])

    def test_o_resto_do_cabecalho_recusa_pela_regra_do_kit_por_ultimo(self):
        for nome, extras in RECUSADOS_NO_KIT.items():
            with self.subTest(nome=nome):
                pc = MOD.conferir(self.candidato(extras, nome=nome))
                self.assertFalse(pc["conforme"])
                self.assertIsNone(pc["manifesto_sha256"])

    def test_listas_daqui_dentro_das_do_kit(self):
        self.assertTrue(Path(plugins.__file__).resolve().is_relative_to(KIT.resolve()))
        self.assertEqual(Path(MOD.KIT.__file__).resolve(), Path(plugins.__file__).resolve(),
                         "o plugin_candidato carrega o kit desta skill")
        self.assertLessEqual(MOD.LICENCAS, plugins.NA_RAIZ_DO_PLUGIN)
        self.assertLessEqual(MOD.CHAVES_DE_SKILL, plugins.CHAVES_DO_FRONTMATTER["skills"])
        self.assertLessEqual(MOD.CHAVES_DE_COMANDO, plugins.CHAVES_DO_FRONTMATTER["commands"])
        self.assertLessEqual(MOD.CHAVES_DE_AGENTE, plugins.CHAVES_DO_FRONTMATTER["agents"])
        self.assertLessEqual(plugins.EXECUTAVEIS, MOD.EXECUTAVEIS)
        self.assertLessEqual(set(MOD.COMPONENTES) | {".claude-plugin"}, plugins.PASTAS_DO_PLUGIN)
        for daqui, do_kit in (("arquivos", "arquivos"), ("arquivo", "bytes_arquivo"), ("total", "bytes"),
                              ("profundidade", "niveis")):
            self.assertLessEqual(MOD.TETO[daqui], plugins.TETO_PLUGIN[do_kit], daqui)
        # As regras comuns da emenda E4, iguais nos dois (o texto do padrão já com os escapes resolvidos).
        self.assertEqual(MOD.SHELL_EMBUTIDO.pattern, plugins._CONTEXTO_DINAMICO.pattern)
        self.assertEqual(MOD.CONTROLE.pattern, plugins._CONTROLE.pattern)
        self.assertEqual(MOD.QUEBRA_ESCONDIDA.pattern, plugins._QUEBRA_ESCONDIDA.pattern)
        self.assertEqual(MOD.FICHA.NOME_PLUGIN.pattern, regras.NOME_PLUGIN.pattern)

    def test_nome_do_plugin_pela_regra_da_ficha(self):
        # O conferir_pasta_do_plugin não olha o nome; o validador da ficha olha (abertura preparar: NOME_PLUGIN).
        for nome in ("demo-Kit_v2", "demo-kit.v2", "demo-" + "x" * 60):
            with self.subTest(nome=nome):
                pasta = self.candidato(nome=nome)
                pc = MOD.conferir(pasta)
                self.assertFalse(pc["conforme"])
                self.assertTrue(any("regra da ficha de aberturas" in m for m in pc["motivos"]), pc["motivos"])
                erros = regras.validar(ficha_com(self.item(pasta, "a" * 64)), projeto="demo")["erros"]
                self.assertTrue(any(e["campo"] == "plugins[0].nome" for e in erros), erros)
        for nome in ("demo-" + "x" * 59, "demo-kit--v2"):  # 64 caracteres; '--' passa na ficha, com o aviso
            with self.subTest(nome=nome):
                pc, _kit = self.implicacao(self.candidato(nome=nome))
                self.assertTrue(pc["conforme"], pc["motivos"])
                self.assertEqual(any("kebab-case" in a for a in pc["avisos"]), "--" in nome, pc["avisos"])

    def test_tetos_do_kit(self):
        base = self.candidato(nome="demo-quinhentos")
        existentes = len(self.arquivos_de(base))
        escrever(base, {f"skills/ola/muitos/n{i:03d}.md": "x\n" for i in range(500 - existentes)})
        self.implicacao(base)
        self.assertTrue(MOD.conferir(base)["conforme"], "500 arquivos: o teto do kit, ainda aceito")
        escrever(base, {"skills/ola/muitos/n-extra.md": "x\n"})
        pc, kit = self.implicacao(base)
        self.assertFalse(pc["conforme"])
        self.assertTrue(any("teto de 500 arquivos" in m for m in pc["motivos"]), pc["motivos"])
        self.assertTrue(kit["erros"])
        mega = 1 << 20
        exato = self.candidato({"skills/ola/grande.md": "x" * mega}, nome="demo-um-mib")
        self.assertTrue(self.implicacao(exato)[0]["conforme"])
        acima = self.candidato({"skills/ola/grande.md": "x" * (mega + 1)}, nome="demo-acima")
        pc, kit = self.implicacao(acima)
        self.assertFalse(pc["conforme"])
        self.assertTrue(any(f"teto de {mega} bytes por arquivo" in m for m in pc["motivos"]), pc["motivos"])
        self.assertTrue(kit["erros"])
        total = self.candidato({f"skills/ola/grandes/g{i:02d}.md": "x" * mega for i in range(16)}, nome="demo-total")
        pc, kit = self.implicacao(total)
        self.assertFalse(pc["conforme"])
        self.assertTrue(any(f"teto de {16 * mega} bytes no total" in m for m in pc["motivos"]), pc["motivos"])
        self.assertTrue(kit["erros"])

    @unittest.skipIf(os.name == "nt", "o bit de execução só existe fora do Windows (o kit também só confere fora)")
    def test_bit_de_execucao_recusa_como_no_kit(self):
        pasta = self.candidato(nome="demo-executavel")
        os.chmod(pasta / "skills" / "ola" / "referencias" / "guia.md", 0o755)
        pc, kit = self.implicacao(pasta)
        self.assertFalse(pc["conforme"])
        self.assertTrue(any(m.startswith("skills/ola/referencias/guia.md") and "bit de execução" in m
                            for m in pc["motivos"]), pc["motivos"])
        self.assertTrue(kit["erros"])
        with self.assertRaises(MOD.CandidatoRecusado) as ctx:
            MOD.manifesto(pasta)
        self.assertIn("bit de execução", str(ctx.exception))


class TestRegraDoCaminhoConfiavel(Base, unittest.TestCase):
    """Item I16: o caminho confiável (o kit, sozinho) recusa o que o plugin_candidato recusa nestes pontos, e a sessão
    recusa pela própria regra (não só pela do kit, por último). Antes, o kit aceitava cada caso de RECUSADOS_NOS_DOIS e
    levantava UnicodeEncodeError com o nome fora do UTF-8."""

    def test_recusados_nos_dois_cada_um_pela_propria_regra(self):
        for nome, (extras, rel) in RECUSADOS_NOS_DOIS.items():
            with self.subTest(nome=nome):
                pasta = self.candidato(extras, nome=nome)
                with mock.patch.object(MOD.KIT, "conferir_pasta_do_plugin") as ultima:  # só as regras daqui
                    pc = MOD.conferir(pasta)
                ultima.assert_not_called()
                self.assertFalse(pc["conforme"])
                self.assertTrue(any(m.startswith(rel) and not m.endswith(MARCA_DO_KIT) for m in pc["motivos"]),
                                pc["motivos"])
                kit = plugins.conferir_pasta_do_plugin(pasta, nome)
                self.assertTrue(any(e["campo"] == f"plugin {nome}: {rel}" for e in kit["erros"]), kit["erros"])
                self.assertIsNone(kit["manifesto_sha256"])

    @unittest.skipIf(os.name == "nt", "o NTFS não guarda esses nomes (no Windows, a face deles é a área privada)")
    def test_face_do_ubuntu_dos_nomes_do_drvfs_recusa_nos_dois(self):
        # Reconferência da integração, rodada 2: a sessão já recusava esses nomes; o kit (o caminho confiável) passa a
        # recusá-los também, para o mesmo candidato dar o mesmo resultado no Windows e no Ubuntu.
        for rel, campo in FACE_DO_UBUNTU.items():
            with self.subTest(rel=rel):
                pasta = self.candidato({rel: "x\n"}, nome="demo-face")
                with mock.patch.object(MOD.KIT, "conferir_pasta_do_plugin") as ultima:  # só as regras daqui
                    pc = MOD.conferir(pasta)
                ultima.assert_not_called()
                self.assertFalse(pc["conforme"])
                self.assertTrue(any(m.startswith(campo) and "Windows" in m for m in pc["motivos"]), pc["motivos"])
                kit = plugins.conferir_pasta_do_plugin(pasta, "demo-face")
                self.assertTrue(any(e["campo"] == f"plugin demo-face: {campo}" and "não funciona igual" in e["motivo"]
                                    for e in kit["erros"]), kit["erros"])
                self.assertIsNone(kit["manifesto_sha256"])

    def test_nome_fora_do_utf8_recusa_nos_dois_sem_excecao(self):
        try:
            pasta = self.candidato({"skills/ola/a\udcff.md": "x\n"}, nome="demo-nome")
        except (OSError, UnicodeError) as exc:
            self.skipTest(f"este sistema de arquivos não guarda nome fora do UTF-8: {exc}")
        pc, kit = self.implicacao(pasta)
        self.assertFalse(pc["conforme"])
        self.assertTrue(any("nome que não é UTF-8" in m and not m.endswith(MARCA_DO_KIT) for m in pc["motivos"]))
        self.assertTrue(any(e["campo"] == "plugin demo-nome: skills/ola/a\\udcff.md" and "não é UTF-8" in e["motivo"]
                            for e in kit["erros"]), kit["erros"])
        for res in (pc, kit):
            json.dumps(res, ensure_ascii=False).encode("utf-8")  # o que se imprime sai em UTF-8
        with self.assertRaises(MOD.CandidatoRecusado):
            MOD.manifesto(pasta)

    def test_a_regra_de_allowed_tools_e_da_mencao_e_a_do_kit(self):
        md = MOD.MARKDOWN  # o kit desta skill, carregado pelo plugin_candidato sob nome próprio
        self.assertEqual(Path(md.__file__).resolve(), (KIT / "fundacao" / "core" / "aberturas_markdown.py").resolve())
        self.assertIs(MOD.ferramentas_do_valor, md.ferramentas_do_valor)
        self.assertIs(MOD._de_fora, md.de_fora)
        self.assertIs(MOD._referencias_de_fora, md.referencias_de_fora)
        self.assertEqual(MOD.FERRAMENTAS_DO_CABECALHO, markdown.FERRAMENTAS_DO_CABECALHO)
        self.assertEqual(MOD.SO_PELA_FICHA, markdown.SO_PELA_FICHA)
        self.assertEqual(MOD.REFERENCIA.pattern, markdown.REFERENCIA.pattern)
        self.assertEqual(md.BOM, markdown.BOM)
        # A mensagem é a mesma nos dois (o titular vê o mesmo motivo na sessão e no caminho confiável).
        pasta = self.candidato(RECUSADOS_NOS_DOIS["demo-at-bash"][0], nome="demo-at-bash")
        daqui = [m.partition(": ")[2] for m in MOD.conferir(pasta)["motivos"]]
        do_kit = [e["motivo"] for e in plugins.conferir_pasta_do_plugin(pasta, "demo-at-bash")["erros"]]
        self.assertEqual(daqui, do_kit)
        self.assertTrue(any("só abre pela ficha de aberturas" in m for m in do_kit), do_kit)


class TestRegraDoKitPorUltimo(Base, unittest.TestCase):
    """O conferir, o revisar e a conferência final do montar passam o candidato pelo kit, depois das regras daqui."""

    def test_erro_do_kit_recusa_um_candidato_conforme_aqui(self):
        pasta = self.candidato()
        real = MOD.KIT.conferir_pasta_do_plugin

        def com_erro(p, nome=None):
            res = real(p, nome)
            return {**res, "erros": [{"campo": f"plugin {nome}: skills/ola/SKILL.md", "motivo": "erro fictício"}],
                    "manifesto_sha256": None}

        with mock.patch.object(MOD.KIT, "conferir_pasta_do_plugin", side_effect=com_erro):
            res = MOD.conferir(pasta)
            texto, revisado = MOD.revisar(pasta)
        self.assertFalse(res["conforme"])
        self.assertEqual((res["manifesto"], res["manifesto_sha256"]), (None, None))
        self.assertEqual(res["motivos"], [f"skills/ola/SKILL.md: erro fictício {MARCA_DO_KIT}"])
        self.assertFalse(revisado["conforme"])
        self.assertIn("nada a listar na ficha", texto)
        self.assertTrue(MOD.conferir(pasta)["conforme"], "sem o erro fictício, conforme")

    def test_manifesto_do_kit_diferente_recusa(self):
        # O kit lê os bytes de novo: um arquivo trocado entre as duas leituras dá outro manifesto e recusa.
        pasta = self.candidato()
        real = MOD.KIT.conferir_pasta_do_plugin
        with mock.patch.object(MOD.KIT, "conferir_pasta_do_plugin",
                               side_effect=lambda p, nome=None: {**real(p, nome), "manifesto_sha256": "0" * 64}):
            res = MOD.conferir(pasta)
        self.assertFalse(res["conforme"])
        self.assertTrue(any("mudou durante a conferência" in m for m in res["motivos"]), res["motivos"])

    def test_nada_de_nome_forte_chega_ao_kit(self):
        # A regra do kit só roda depois que as daqui aceitaram: o nome forte nunca é lido, nem por ela.
        pasta = self.candidato({"skills/ola/id_rsa": "chave fictícia\n"})
        with mock.patch.object(MOD.KIT, "conferir_pasta_do_plugin") as kit:
            self.assertFalse(MOD.conferir(pasta)["conforme"])
        kit.assert_not_called()

    def test_montar_recusa_pela_regra_do_kit_e_nao_deixa_nada(self):
        origem = self.proj / "importado" / ".claude"
        escrever(origem, {"skills/ola/SKILL.md": skill("name: ola\ndescription: Usa hooks do git (fictício)."),
                          "commands/resumo.md": COMANDO_OK})
        with self.assertRaises(MOD.CandidatoRecusado) as ctx:
            MOD.montar(self.raiz, "demo", "kit", origem)
        motivos = ctx.exception.motivos
        self.assertTrue(motivos[0].startswith("a conferência do candidato montado recusou"), motivos)
        self.assertTrue(any(m.startswith("skills/ola/SKILL.md") and m.endswith(MARCA_DO_KIT) for m in motivos),
                        motivos)
        self.assertEqual(list((self.proj / "plugins-candidatos").iterdir()), [], "nem o candidato nem o temporário")

    def test_montar_avisa_da_licenca_que_nao_vem(self):
        origem = self.proj / "importado" / ".claude"
        escrever(origem, {"skills/ola/SKILL.md": SKILL_OK, "LICENSE": "Licença fictícia.\n",
                          "NOTICE": "Aviso fictício.\n", "COPYING.txt": "Cópia fictícia.\n"})
        res = MOD.montar(self.raiz, "demo", "kit", origem)
        destino = Path(res["candidato"])
        self.assertEqual(sorted(res["nao_copiados"]), ["COPYING.txt", "NOTICE"])
        self.assertTrue(any("NOTICE" in a and "só LICENSE, LICENSE.md ou LICENSE.txt" in a for a in res["avisos"]),
                        res["avisos"])
        self.assertTrue((destino / "LICENSE").is_file())
        self.assertFalse((destino / "NOTICE").exists())
        self.implicacao(destino)

    def test_carrega_o_kit_sem_mexer_no_fundacao_nem_no_sys_path(self):
        codigo = ("import importlib.util, json, sys\n"
                  "antes = list(sys.path)\n"
                  f"spec = importlib.util.spec_from_file_location('pc', {str(SCRIPTS / 'plugin_candidato.py')!r})\n"
                  "m = importlib.util.module_from_spec(spec)\n"
                  "spec.loader.exec_module(m)\n"
                  "print(json.dumps({'fundacao': sorted(n for n in sys.modules if n.split('.')[0] == 'fundacao'),"
                  " 'sys_path': sys.path == antes, 'kit': m.KIT.__name__, 'arquivo': m.KIT.__file__}))\n")
        r = subprocess.run([sys.executable, "-B", "-c", codigo], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=ENV, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        saida = json.loads(r.stdout)
        self.assertEqual((saida["fundacao"], saida["sys_path"], saida["kit"]),
                         ([], True, "_plugin_candidato_kit.core.aberturas_plugins"))
        self.assertEqual(Path(saida["arquivo"]).resolve(),
                         (KIT / "fundacao" / "core" / "aberturas_plugins.py").resolve())


# Skills com scripts (1.7.11, lote S1): conforme aqui, com --com-scripts, implica sem erro no kit com a sugestão da ficha.
SKILL_BUSCA = "---\nname: busca\ndescription: Busca (skill fictícia).\n---\n\nChame o executor.\n"
COM_SCRIPT = {"skills/busca/SKILL.md": SKILL_BUSCA, "skills/busca/scripts/buscar.py": "print('ok')\n"}
LOCK_COM_RODAS = "# rodas: outputs/rodas-busca\nalfa==1.0 \\\n    --hash=sha256:" + "a" * 64 + "\n"
ACEITOS_COM_SCRIPTS = {
    "demo-s-sem-pacotes": {},
    "demo-s-com-lock": {"skills/busca/requirements.lock": LOCK_COM_RODAS},
    "demo-s-dois": {"skills/busca/scripts/coletar_tudo.py": "print(1)\n"},
    "demo-s-bom-e-cookie": {"skills/busca/scripts/buscar.py": chr(0xFEFF) + "# coding: utf-8\nprint('ok')\n"},
    "demo-s-crlf": {"skills/busca/scripts/buscar.py": "print('ok')\r\n"},
    "demo-s-duas-skills": {"skills/outra/SKILL.md": SKILL_BUSCA.replace("busca", "outra"),
                           "skills/outra/scripts/x.py": "print(2)\n"},
}
# Recusados aqui e no kit, mesmo que a ficha liste o arquivo: {nome: arquivos a mais}.
RECUSADOS_COM_SCRIPTS = {
    "demo-r-shebang": {"skills/busca/scripts/buscar.py": "#!/usr/bin/env python3\nprint(1)\n"},
    "demo-r-fora-do-lugar": {"skills/busca/buscar.py": "print(1)\n"},
    "demo-r-subpasta": {"skills/busca/scripts/sub/x.py": "print(1)\n"},
    "demo-r-maiuscula": {"skills/busca/scripts/Coletar.py": "print(1)\n"},
    "demo-r-init": {"skills/busca/scripts/__init__.py": "print(1)\n"},
    "demo-r-agente": {"agents/x.py": "print(1)\n"},
    "demo-r-shell": {"skills/busca/scripts/rodar.sh": "echo ficticio\n"},
    "demo-r-js": {"skills/busca/scripts/rodar.js": "console.log(1)\n"},
    "demo-r-pyc": {"skills/busca/scripts/rodar.pyc": "x"},
    "demo-r-cookie": {"skills/busca/scripts/buscar.py": "# coding: latin-1\nprint(1)\n"},
    "demo-r-direcao": {"skills/busca/scripts/buscar.py": "x = '" + chr(0x202e) + "'\n"},
    "demo-r-cr": {"skills/busca/scripts/buscar.py": "x = 1\ry = 2\n"},
    "demo-r-lock-opcao": {"skills/busca/requirements.lock": "# rodas: x\n-e .\n"},
    "demo-r-lock-sem-hash": {"skills/busca/requirements.lock": "# rodas: x\nalfa==1.0\n"},
    "demo-r-lock-url": {"skills/busca/requirements.lock": "# rodas: x\nalfa @ https://x.example/a.whl\n"},
    "demo-r-lock-fora": {"skills/busca/sub/requirements.lock": LOCK_COM_RODAS},
}


class TestComScripts(Base, unittest.TestCase):
    def sugestao(self, pasta: Path) -> tuple[dict, dict]:
        pc = MOD.conferir(pasta, com_scripts=True)
        return pc, {**self.item(pasta, pc["manifesto_sha256"]), "skills_com_scripts": pc["skills_com_scripts_para_a_ficha"]}

    def lista_manual(self, pasta: Path) -> list:
        """Uma lista que lista TODO .py e todo lock do disco, onde estiverem (o pior caso para o kit)."""
        achados = {p.relative_to(pasta).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in pasta.rglob("*") if p.is_file()}
        py = [r for r in achados if r.endswith((".py", ".sh", ".js", ".pyc"))]
        locks = [r for r in achados if r.endswith("requirements.lock")]
        dep = locks and {"lock": locks[0], "lock_sha256": achados[locks[0]], "rodas": "outputs/rodas", "python": "3.12",
                         "pacotes": 1}
        return [{"skill": "busca", "skill_md_sha256": achados.get("skills/busca/SKILL.md", "0" * 64),
                 "scripts": [{"nome": "x", "caminho": r, "sha256": achados[r], "modo": "sessao"} for r in py],
                 **({"dependencias": dep} if locks else {})}]

    def test_conforme_aqui_implica_sem_erro_no_kit_com_a_sugestao(self):
        for nome, extras in ACEITOS_COM_SCRIPTS.items():
            with self.subTest(aceito=nome):
                pasta = self.candidato({**COM_SCRIPT, **extras}, nome=nome)
                pc, item = self.sugestao(pasta)
                self.assertTrue(pc["conforme"], pc["motivos"])
                kit = plugins.conferir_pasta_do_plugin(pasta, nome, item["skills_com_scripts"])
                self.assertEqual(kit["erros"], [], nome)
                self.assertEqual(pc["manifesto_sha256"], kit["manifesto_sha256"])
                self.assertEqual(regras.validar(ficha_com(item), projeto="demo")["erros"], [], nome)
                self.assertEqual(plugins.conferir_plugin(self.proj, item)["erros"], [], nome)
                sem_lista = plugins.conferir_pasta_do_plugin(pasta, nome)  # o kit, sem o item da ficha, recusa o código
                self.assertTrue(sem_lista["erros"], nome)
                self.assertFalse(MOD.conferir(pasta)["conforme"], "sem --com-scripts o .py recusa também aqui")

    def test_recusado_aqui_e_no_kit_mesmo_com_a_ficha_listando_o_arquivo(self):
        for nome, extras in RECUSADOS_COM_SCRIPTS.items():
            with self.subTest(recusado=nome):
                pasta = self.candidato({**COM_SCRIPT, **extras}, nome=nome)
                self.assertFalse(MOD.conferir(pasta, com_scripts=True)["conforme"], nome)
                kit = plugins.conferir_pasta_do_plugin(pasta, nome, self.lista_manual(pasta))
                self.assertTrue(kit["erros"], f"{nome}: o kit devia recusar mesmo listado")

    def test_sem_os_arquivos_de_codigo_a_opcao_nao_muda_nada(self):
        pasta = self.candidato(nome="demo-md")
        a, b = MOD.conferir(pasta), MOD.conferir(pasta, com_scripts=True)
        self.assertEqual({k: v for k, v in a.items()}, {k: v for k, v in b.items()})
        self.assertEqual(b["skills_com_scripts_para_a_ficha"], [])

    def test_montar_com_a_opcao_e_a_linha_da_ficha_que_o_kit_aceita(self):
        origem = self.proj / "importado" / "busca"
        escrever(origem, {"SKILL.md": SKILL_BUSCA, "scripts/buscar.py": "print('ok')\n"})
        res = MOD.montar(self.raiz, "demo", "busca", origem, com_scripts=True)
        item = {**res["ficha"], "skills_com_scripts": res["skills_com_scripts_para_a_ficha"]}
        self.assertEqual(regras.validar(ficha_com(item), projeto="demo")["erros"], [])
        self.assertEqual(plugins.conferir_plugin(self.proj, item)["erros"], [])
        self.assertEqual(res["manifesto_sha256"], plugins.conferir_plugin(self.proj, item)["manifesto_sha256"])


if __name__ == "__main__":
    unittest.main()
