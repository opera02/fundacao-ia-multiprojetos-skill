"""plugin_candidato.py no DrvFs (1.7.10; emenda E9 dos contratos do lote 2): numa montagem 9p ou drvfs sem a opção
metadata (o DrvFs do WSL, /mnt/<letra>), todo arquivo aparece 0777 e o bit de execução não prova nada; o `conferir`, o
`revisar`, o `manifesto` e a conferência final do `montar` decidem pelo conteúdo (`#!`, ELF ou MZ no começo), pela
regra do kit (aberturas_plugins.bit_de_execucao_vale, que lê o /proc/mounts sem executar programa). No ext4 e com a
opção metadata, o bit, como antes; no Windows, nenhum dos dois. Antes, com a raiz em /mnt/e, todo candidato era
recusado pelo bit, e o `montar` nunca terminava ali.

O /proc/mounts é fictício: o MONTAGENS do kit trocado na cópia que o plugin_candidato carrega e na do teste. A sonda no
DrvFs de verdade roda com FUNDACAO_SONDA_DRVFS apontando uma pasta temporária de /mnt/<letra> (sem a variável,
pulada). Pastas descartáveis com dados fictícios; nada do candidato é executado.

Revisão da integração, rodada 2: a sessão confere o conteúdo em todo sistema, também no Windows e no ext4
(TestConteudoEmTodoSistema); só o bit depende da montagem. Reconferência da integração, rodada 2: na sonda, o nome que
o DrvFs troca (U+F03A no Windows, ':' no Ubuntu) recusa na sessão e no kit.
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import KIT
from test_plugin_candidato import MOD, Fundacao, escrever

if str(KIT) not in sys.path:  # o kit desta skill, pelo caminho (o mesmo que a ferramenta do titular carrega)
    sys.path.insert(0, str(KIT))
from fundacao.core import aberturas_plugins as plugins  # noqa: E402

SONDA_DRVFS = "FUNDACAO_SONDA_DRVFS"
MARCA_DO_KIT = "(regra do kit, aberturas_plugins.conferir_pasta_do_plugin)"
CONTEUDOS = (("skills/ola/referencias/rodar.md", b"#!/bin/sh\necho ficticio\n"), ("LICENSE", b"\x7fELF\x02\x01x"),
             ("commands/x.md", b"MZ fict\xc3\xadcio\n"))


def montagem(pasta: Path, opcoes: str = "rw,noatime,aname=drvfs;path=C:\\;uid=1000;gid=1000") -> str:
    """Um /proc/mounts fictício: a raiz em ext4 e `pasta` (resolvida, com o espaço escapado) numa montagem 9p."""
    real = os.path.realpath(pasta).replace(" ", "\\040")
    return f"/dev/sdd / ext4 rw,relatime 0 0\nC:\\134 {real} 9p {opcoes} 0 0\n"


def tudo_0777(pasta: Path) -> None:
    for arquivo in pasta.rglob("*"):
        if arquivo.is_file():
            os.chmod(arquivo, 0o777)  # como o DrvFs sem metadata mostra todo arquivo


@unittest.skipIf(os.name == "nt", "o bit de execução só existe fora do Windows")
class TestBitNoDrvfs(Fundacao, unittest.TestCase):
    def setUp(self):
        super().setUp()
        if MOD._sem_prova_do_bit(self.base):  # a contraprova pede os temporários fora do DrvFs (ext4, tmpfs)
            self.skipTest("os temporários destes testes ficam numa montagem sem metadata")

    def montagens(self, texto: str) -> None:
        arquivo = self.base / "mounts-ficticio"
        arquivo.write_text(texto, encoding="utf-8")
        for modulo in (MOD.KIT, plugins):  # a cópia do kit que o plugin_candidato carrega e a do teste
            trocado = mock.patch.object(modulo, "MONTAGENS", str(arquivo))
            trocado.start()
            self.addCleanup(trocado.stop)

    def test_conferir_revisar_e_manifesto_decidem_pelo_conteudo(self):
        pasta = self.candidato()
        tudo_0777(pasta)
        antes = MOD.conferir(pasta)  # contraprova: no ext4 o bit recusa (e recusava também no DrvFs)
        self.assertFalse(antes["conforme"])
        self.assertTrue(any("bit de execução" in m for m in antes["motivos"]), antes["motivos"])
        with self.assertRaises(MOD.CandidatoRecusado):
            MOD.manifesto(pasta)
        self.montagens(montagem(self.base))
        self.assertTrue(MOD._sem_prova_do_bit(pasta))
        res = MOD.conferir(pasta)
        self.assertTrue(res["conforme"], res["motivos"])
        self.assertEqual(res["manifesto_sha256"], MOD.manifesto(pasta)[1])
        self.assertEqual(res["manifesto_sha256"], plugins.conferir_pasta_do_plugin(pasta, pasta.name)["manifesto_sha256"])
        self.assertTrue(MOD.revisar(pasta)[1]["conforme"])
        for rel, dados in CONTEUDOS:
            with self.subTest(rel=rel):
                alvo = pasta.joinpath(*rel.split("/"))
                original = alvo.read_bytes() if alvo.exists() else None
                alvo.write_bytes(dados)
                os.chmod(alvo, 0o777)
                res = MOD.conferir(pasta)
                self.assertFalse(res["conforme"])
                self.assertTrue(any(m.startswith(rel) and "executável pelo conteúdo" in m
                                    and not m.endswith(MARCA_DO_KIT) for m in res["motivos"]), res["motivos"])
                with self.assertRaises(MOD.CandidatoRecusado) as ctx:
                    MOD.manifesto(pasta)
                self.assertIn("executável pelo conteúdo", str(ctx.exception))
                kit = plugins.conferir_pasta_do_plugin(pasta, pasta.name)["erros"]
                self.assertTrue(any("pelo conteúdo" in e["motivo"] for e in kit), kit)
                if original is None:
                    alvo.unlink()
                else:
                    alvo.write_bytes(original)
        self.assertTrue(MOD.conferir(pasta)["conforme"])
        self.montagens(montagem(self.base, "rw,aname=drvfs;path=C:\\;metadata;uid=1000"))  # com metadata, o bit
        self.assertTrue(any("bit de execução" in m for m in MOD.conferir(pasta)["motivos"]))

    def test_no_ext4_a_regra_de_antes(self):
        # No ext4 o bit vale, como antes: com o bit, recusa pelo bit. Aperto da revisão da integração, rodada 2: o
        # Markdown que começa com '#!', sem o bit, passava aqui e agora recusa pelo conteúdo, em todo sistema (o kit no
        # Ubuntu, lendo a raiz pela /mnt/<letra>, o recusa; TestConteudoEmTodoSistema).
        pasta = self.candidato({"skills/ola/referencias/rodar.md": "#!/bin/sh\necho ficticio\n"})
        os.chmod(pasta / "skills" / "ola" / "referencias" / "rodar.md", 0o644)
        self.assertFalse(MOD._sem_prova_do_bit(pasta))
        sem_bit = MOD.conferir(pasta)
        self.assertFalse(sem_bit["conforme"])
        self.assertTrue(any("executável pelo conteúdo" in m for m in sem_bit["motivos"]), sem_bit["motivos"])
        os.chmod(pasta / "skills" / "ola" / "referencias" / "rodar.md", 0o755)
        self.assertTrue(any("bit de execução" in m for m in MOD.conferir(pasta)["motivos"]))


class TestConteudoEmTodoSistema(Fundacao, unittest.TestCase):
    """Revisão da integração, rodada 2: a conferência pelo conteúdo (#!, ELF ou MZ no começo) vale na sessão em todo
    sistema; só o bit depende da montagem. Antes, a sessão do Windows (e a do ext4) dava conforme a um candidato que o
    kit no Ubuntu, que é o do instalador do host lendo a raiz pela /mnt/<letra>, recusa "pelo conteúdo": o titular
    assinaria uma ficha que o host não instala. A sessão pode ser mais estrita que o kit (emenda E4)."""

    SONDADOS = {"skills/ola/referencias/guia.md": "#!important: texto fictício que começa como script.\n",
                "commands/resumo.md": "MZ-1000 é o modelo fictício do relatório.\n"}

    def test_markdown_que_comeca_como_executavel_recusa_pela_regra_daqui(self):
        pasta = self.candidato(self.SONDADOS)
        res = MOD.conferir(pasta)
        self.assertFalse(res["conforme"])
        for rel in self.SONDADOS:
            with self.subTest(rel=rel):
                self.assertTrue(any(m.startswith(rel) and "executável pelo conteúdo" in m
                                    and not m.endswith(MARCA_DO_KIT) for m in res["motivos"]), res["motivos"])
        with self.assertRaises(MOD.CandidatoRecusado) as ctx:
            MOD.manifesto(pasta)
        self.assertIn("executável pelo conteúdo", str(ctx.exception))
        self.assertFalse(MOD.revisar(pasta)[1]["conforme"])
        # O kit fora do DrvFs sem metadata (o Windows, o ext4 destes testes) aceita o mesmo candidato: a sessão é a
        # mais estrita, e o kit lendo pela /mnt/<letra> (no Ubuntu) recusaria.
        if os.name == "nt" or not MOD._sem_prova_do_bit(pasta):
            self.assertEqual(plugins.conferir_pasta_do_plugin(pasta, pasta.name)["erros"], [])

    def test_montar_recusa_antes_de_copiar(self):
        origem = self.origem_arvore({"skills/ola/referencias/guia.md": self.SONDADOS["skills/ola/referencias/guia.md"]})
        with self.assertRaises(MOD.CandidatoRecusado) as ctx:
            MOD.montar(self.raiz, "demo", "kit", origem)
        self.assertTrue(any("executável pelo conteúdo" in m for m in ctx.exception.motivos), ctx.exception.motivos)
        candidatos = self.proj / "plugins-candidatos"
        self.assertFalse(candidatos.exists() and any(candidatos.iterdir()), "nada copiado")


class TestSondaNoDrvfsDeVerdade(Fundacao, unittest.TestCase):
    """Emenda E9 no DrvFs de verdade (passo opcional: FUNDACAO_SONDA_DRVFS=<pasta temporária em /mnt/<letra>>): o
    candidato montado e conferido ali, como numa sessão com a raiz em /mnt/e."""

    @unittest.skipUnless(os.environ.get(SONDA_DRVFS) and os.name != "nt",
                         "sonda opcional: FUNDACAO_SONDA_DRVFS com uma pasta temporária num DrvFs (/mnt/<letra>)")
    def test_montar_e_conferir_no_drvfs(self):
        base = Path(tempfile.mkdtemp(prefix="sonda-e9-candidato-", dir=os.environ[SONDA_DRVFS]))
        self.addCleanup(apagar_no_drvfs, base)
        self.raiz = base / "fundacao"
        self.proj = self.raiz / "projects" / "demo"
        self.proj.mkdir(parents=True)
        origem = self.origem_arvore()
        if MOD.KIT.bit_de_execucao_vale(origem):
            self.skipTest(f"{base}: não é uma montagem 9p ou drvfs sem metadata")
        res = MOD.montar(self.raiz, "demo", "kit", origem)  # antes: a cópia (0o555 no DrvFs) recusava pelo bit
        destino = Path(res["candidato"])
        self.assertTrue(os.stat(destino / "skills" / "ola" / "SKILL.md").st_mode & 0o111, "o DrvFs mostra o bit")
        self.assertTrue(MOD.conferir(destino)["conforme"])
        self.assertEqual(MOD.manifesto(destino)[1], res["manifesto_sha256"])
        self.assertEqual(plugins.conferir_pasta_do_plugin(destino, destino.name)["manifesto_sha256"],
                         res["manifesto_sha256"])
        escrever(destino, {"skills/ola/referencias/rodar.md": "#!/bin/sh\necho ficticio\n"})
        self.assertTrue(any("executável pelo conteúdo" in m for m in MOD.conferir(destino)["motivos"]))

    @unittest.skipUnless(os.environ.get(SONDA_DRVFS) and os.name != "nt",
                         "sonda opcional: FUNDACAO_SONDA_DRVFS com uma pasta temporária num DrvFs (/mnt/<letra>)")
    def test_nome_que_o_drvfs_troca_recusa_nos_dois(self):
        # Reconferência da integração, rodada 2: o nome que o Windows guarda com U+F03A aparece no Ubuntu com ':' (e o
        # que o Ubuntu grava com ':' fica com U+F03A no Windows). Pela /mnt/<letra>, a sessão e o kit recusam a face do
        # Ubuntu; a do Windows (a área privada) recusa nos dois pela mesma regra (test_plugin_regra_unica_1710).
        base = Path(tempfile.mkdtemp(prefix="sonda-nome-candidato-", dir=os.environ[SONDA_DRVFS]))
        self.addCleanup(apagar_no_drvfs, base)
        self.raiz = base / "fundacao"
        self.proj = self.raiz / "projects" / "demo"
        self.proj.mkdir(parents=True)
        pasta = self.candidato({f"skills/ola/guia{chr(0xF03A)}x.md": "x\n"})
        if "guia:x.md" not in os.listdir(pasta / "skills" / "ola"):
            self.skipTest(f"{base}: o nome não foi trocado (não é o DrvFs do WSL)")
        with mock.patch.object(MOD.KIT, "conferir_pasta_do_plugin") as ultima:  # só as regras da sessão
            pc = MOD.conferir(pasta)
        ultima.assert_not_called()
        self.assertFalse(pc["conforme"])
        self.assertTrue(any(m.startswith("skills/ola/guia:x.md") and "Windows" in m for m in pc["motivos"]),
                        pc["motivos"])
        kit = plugins.conferir_pasta_do_plugin(pasta, pasta.name)
        self.assertTrue(any(e["campo"] == f"plugin {pasta.name}: skills/ola/guia:x.md" and "não funciona igual" in
                            e["motivo"] for e in kit["erros"]), kit["erros"])
        self.assertIsNone(kit["manifesto_sha256"])


def apagar_no_drvfs(base: Path) -> None:
    """Apaga a pasta da sonda: o DrvFs guarda o 0o444 do `montar` como somente leitura, que o Windows não apaga."""
    for raiz, pastas, arquivos in os.walk(base):
        for nome in (*pastas, *arquivos):
            try:
                os.chmod(os.path.join(raiz, nome), stat.S_IRWXU)
            except OSError:
                pass
    shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
