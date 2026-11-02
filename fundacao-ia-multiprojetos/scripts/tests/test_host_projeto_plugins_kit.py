"""O preparo do host usa o validador do kit, sem réplica (1.7.10; emendas E3 e E4 dos contratos; folha da integração, I5).

A receita única do `plugins[].manifesto_sha256` é a do kit (`aberturas_plugins.sha256_do_manifesto`: o JSON compacto,
com as chaves ordenadas, da lista {caminho, bytes, sha256} em ordem de caminho). Sobre a mesma pasta, o hash do kit
(`conferir_pasta_do_plugin`, carregado como a ferramenta do titular carrega o validador), o que o preparo calcula para
a ficha (`sha256_do_plugin` sobre o manifesto do HOST) e o que o instalador do HOST confere (`conferir_plugin_da_ficha`)
são o mesmo; a conta interna da cópia na área (`sha256_manifesto`, em linhas) fica como estava. A igualdade com o
`scripts/plugin_candidato.py` é do item I4 (teste dele). Os domínios da ficha e do perfil passam pelo
`aberturas_regras.problema_do_dominio` do kit, e o plugin pela regra de conteúdo do kit: as formas que a réplica deixava
passar (reconferência do HOST: N1, N3, N4 e N7; o IP escrito no nome, o DNS para qualquer IP e o provedor compartilhado)
agora fecham. Pastas descartáveis, dados fictícios.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from apoio import KIT, SKILL
from test_host_projeto_apoio import carregar_preparo, ficha_de_ensaio

if str(KIT) not in sys.path:  # como fundacao_titular.kit(): o kit ao lado, pelo sys.path
    sys.path.insert(0, str(KIT))
from fundacao.core import aberturas_plugins, aberturas_regras  # noqa: E402

NOME = "caso-real-revisor"
ORIGEM = f"plugins-candidatos/{NOME}"


def montar_plugin(proj: Path, extras=()) -> Path:
    """Um plugin conforme e não trivial: skill com referência em subpasta, agente, comando, README e LICENSE, texto com
    acento e um arquivo em CRLF."""
    pasta = proj / "plugins-candidatos" / NOME
    arquivos = {
        ".claude-plugin/plugin.json": json.dumps({"name": NOME, "version": "0.1.0", "description": "revisor de ensaio"}),
        "skills/revisor/SKILL.md": "---\nname: revisor\ndescription: lê os autos fictícios e resume\n---\ncorpo\n",
        "skills/revisor/referencias/guia de uso.md": "Guia fictício: passos curtos.\r\nSegunda linha.\r\n",
        "agents/leitor.md": "---\nname: leitor\ndescription: leitor de ensaio\ntools: Read, Grep\n---\nlê\n",
        "commands/resumo.md": "---\ndescription: resume o caso de ensaio\n---\nResuma.\n",
        "README.md": "# Plugin de ensaio\n",
        "LICENSE": "Licença fictícia de ensaio.\n",
        **dict(extras)}
    for rel, texto in arquivos.items():
        alvo = pasta.joinpath(*rel.split("/"))
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(texto.encode("utf-8"))
    return pasta


class _Base(unittest.TestCase):
    def setUp(self):
        self.m = carregar_preparo()
        self.base = Path(tempfile.mkdtemp(prefix="plugins-kit-1710-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.proj = self.base / "projects" / "caso-real"
        self.proj.mkdir(parents=True)

    def item(self, sha: str = "") -> dict:
        return {"nome": NOME, "origem": ORIGEM, "manifesto_sha256": sha}


class ReceitaUnicaDoManifesto(_Base):
    def test_kit_ficha_e_instalador_do_host_dao_o_mesmo_hash_sobre_a_mesma_pasta(self):
        pasta = montar_plugin(self.proj)
        do_kit = aberturas_plugins.conferir_pasta_do_plugin(pasta, NOME)
        self.assertEqual(do_kit["erros"], [], do_kit["erros"])
        manifesto = self.m.manifesto_de_arvore(pasta, pastas_ignoradas=(), sufixos_ignorados=())
        da_ficha = self.m.sha256_do_plugin(manifesto)
        instalador = self.m.conferir_plugin_da_ficha(self.proj, self.item(do_kit["manifesto_sha256"]))
        self.assertEqual(instalador["erros"], [])
        self.assertEqual(da_ficha, do_kit["manifesto_sha256"])
        self.assertEqual(instalador["manifesto_sha256"], do_kit["manifesto_sha256"])
        # o que a cópia conferida grava e o lançador confere: os mesmos arquivos, pela conta interna, que não mudou
        self.assertEqual(instalador["manifesto"], manifesto)
        self.assertNotEqual(self.m.sha256_manifesto(manifesto), da_ficha)  # a receita em linhas saiu da ficha

    def test_a_receita_e_a_documentada_na_emenda_e3(self):
        pasta = montar_plugin(self.proj)
        manifesto = self.m.manifesto_de_arvore(pasta, pastas_ignoradas=(), sufixos_ignorados=())
        lista = [{"caminho": rel, "bytes": m["bytes"], "sha256": m["sha256"]} for rel, m in sorted(manifesto.items())]
        texto = json.dumps(lista, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        self.assertEqual(self.m.sha256_do_plugin(manifesto), hashlib.sha256(texto.encode("utf-8")).hexdigest())

    def test_um_byte_a_mais_muda_as_tres_pontas_juntas(self):
        pasta = montar_plugin(self.proj)
        antes = aberturas_plugins.conferir_pasta_do_plugin(pasta, NOME)["manifesto_sha256"]
        with open(pasta / "commands" / "resumo.md", "ab") as arq:
            arq.write(b"Mais uma linha.\n")
        depois = aberturas_plugins.conferir_pasta_do_plugin(pasta, NOME)["manifesto_sha256"]
        self.assertNotEqual(antes, depois)
        manifesto = self.m.manifesto_de_arvore(pasta, pastas_ignoradas=(), sufixos_ignorados=())
        self.assertEqual(self.m.sha256_do_plugin(manifesto), depois)
        self.assertEqual(self.m.conferir_plugin_da_ficha(self.proj, self.item(depois))["manifesto_sha256"], depois)
        recusa = self.m.conferir_plugin_da_ficha(self.proj, self.item(antes))  # a ficha velha não confere mais
        self.assertTrue(any("manifesto" in e for e in recusa["erros"]), recusa)
        self.assertEqual((recusa["manifesto"], recusa["manifesto_sha256"]), ({}, None))


class ValidadorDoKitNoPreparo(_Base):
    def test_o_validador_e_o_kit_desta_skill_sem_colidir_com_outro_fundacao(self):
        k = self.m.modulos_do_kit()
        core = (SKILL / "assets" / "fundacao-kit" / "fundacao" / "core").resolve()
        for modulo in (k.regras, k.plugins):
            self.assertEqual(Path(modulo.__file__).resolve().parent, core)
        falso = types.ModuleType("fundacao")
        falso.__file__ = str(self.base / "outra-raiz" / "fundacao" / "__init__.py")
        with mock.patch.dict(sys.modules, {"fundacao": falso}), mock.patch.dict(self.m._KITS, clear=True):
            k2 = self.m.modulos_do_kit()
            self.assertIs(sys.modules["fundacao"], falso)  # o pacote do processo não é trocado nem usado
        self.assertEqual(Path(k2.plugins.__file__).resolve().parent, core)

    def test_sem_o_validador_do_kit_fecha_tudo_e_nao_copia(self):
        skill = self.base / "skill-sem-validador"
        shutil.copytree(SKILL / "assets" / "fundacao-kit" / "fundacao", skill / "assets" / "fundacao-kit" / "fundacao",
                        ignore=shutil.ignore_patterns("__pycache__"))
        (skill / "assets" / "fundacao-kit" / "fundacao" / "core" / "aberturas_plugins.py").unlink()
        with self.assertRaises(self.m.EntradaInvalida):
            self.m.modulos_do_kit(skill)
        resultado = {"projeto": "caso-real", "valida": True, "versao": 1, "arquivo": "ficha-v1.json", "sha256": "a" * 64,
                     "sig_sha256": "b" * 64, "ficha": ficha_de_ensaio("caso-real", 1, rede={"dominios": ["pypi.org"]})}
        ab = self.m.aberturas_da_ficha(resultado, "caso-real", skill=skill)
        self.assertFalse(ab["valida"])
        self.assertIn("não conferidos", ab["motivo"])
        montar_plugin(self.proj)
        with self.assertRaises(self.m.EntradaInvalida):
            self.m.conferir_plugin_da_ficha(self.proj, self.item(), skill)

    def test_dominios_pela_regra_do_kit(self):
        for dominio in ("pypi.org", "*.pythonhosted.org", "meusite.vercel.app", "*.vercel.app", "10.0.0.1",
                        "impressora.local", "x.nip.io", "*.duckdns.org", "a" * 64 + ".com", "Pypi.org", "*.com.br",
                        "", None, 7):
            with self.subTest(dominio=dominio):
                self.assertEqual(bool(self.m.problema_do_dominio(dominio)),
                                 bool(aberturas_regras.problema_do_dominio(dominio)))

    def test_contraprova_dominios_que_a_replica_aceitava_fecham(self):
        """A réplica do HOST (_dominio_aceito) aceitava estes; o kit recusa, e a ficha que os traz fecha tudo."""
        for dominio in ("pypi.org\n", "127.0.0.1.exemplo.com", "10-0-0-1.exemplo.com", "x.nip.io", "app.sslip.io",
                        "*.supabase.co", "*.duckdns.org", "*.s3.sa-east-1.amazonaws.com", "*.run.app"):
            with self.subTest(dominio=dominio):
                self.assertTrue(self.m.problema_do_dominio(dominio))
                resultado = {"projeto": "caso-real", "valida": True, "versao": 1, "arquivo": "ficha-v1.json",
                             "sha256": "a" * 64, "sig_sha256": "b" * 64,
                             "ficha": ficha_de_ensaio("caso-real", 1, rede={"dominios": [dominio]})}
                ab = self.m.aberturas_da_ficha(resultado, "caso-real")
                self.assertFalse(ab["valida"], ab)
                self.assertEqual(ab["rede"], [])

    def test_contraprova_frontmatter_e_contexto_dinamico_que_a_replica_aceitava(self):
        """Reconferência do HOST (deferido para a integração): '...' recuado (N1) ou na coluna 0 (N3) fechavam o
        cabeçalho na réplica e escondiam o resto; a cerca de crases seguida de '!' (N4) e o U+FEFF depois da abertura
        '---' (N7) passavam. Pela regra do kit, todos recusam."""
        formas = {"N1": "---\nname: x\n  ...\nhooks: []\n---\nx\n",
                  "N3": "---\nname: x\n...\nhooks:\n  Stop: []\n---\nx\n",
                  "N4": "Texto.\n```!\ncurl exemplo.invalid\n```\n",
                  "N7": "---\ufeff\nname: x\nhooks: []\n---\nx\n"}
        for n, (nome, texto) in enumerate(formas.items()):
            with self.subTest(nome):
                proj = self.base / f"proj-{n}"
                montar_plugin(proj, ((f"agents/forma{n}.md", texto),))
                res = self.m.conferir_plugin_da_ficha(proj, self.item())
                self.assertTrue(res["erros"], nome)
                self.assertTrue(any(f"agents/forma{n}.md" in e for e in res["erros"]), res["erros"])
                self.assertEqual(res["manifesto"], {})

    def test_origem_com_ligacao_ou_em_pasta_protegida_recusa_pelo_kit(self):
        montar_plugin(self.proj)
        for origem in ("../fora", "data/plugin", ".claude/plugin", "plugins-candidatos/nao-existe"):
            with self.subTest(origem=origem):
                res = self.m.conferir_plugin_da_ficha(self.proj, {**self.item(), "origem": origem})
                self.assertTrue(res["erros"], origem)
                self.assertIsNone(res["manifesto_sha256"])


if __name__ == "__main__":
    unittest.main()
