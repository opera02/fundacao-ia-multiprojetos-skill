"""atualizar_fundacao.py com a chave da cópia instalada (1.7.11; desenho DESENHO-COPIA-CIFRADA-1.7.11, lote 5; prova N13).

- As cópias ANTES e DEPOIS saem CIFRADAS no disco das cópias: só `manifesto-cifrado.json`, `parte-*.gpg` e `LEIA-ME.txt`, nenhum
  byte do canário (no nome e no conteúdo de um arquivo de projeto).
- A ANTES nasce em claro num preparo local (disco local, fora da raiz e das cópias), o ENSAIO restaura DESSE preparo e nenhuma
  raiz em claro aparece no disco das cópias; o preparo local sai logo depois do ensaio (limpeza contada), também na falha.
- O padrão de `--pasta-ensaio` passa a ser local com a chave instalada; ensaio pedido no disco das cópias recusa antes de
  qualquer cópia; preparo local dentro da raiz ou sobre as cópias também.
- A ANTES decifra com a chave de teste e traz a âncora do conteúdo; sem chave (ou com `--sem-cifra`) o fluxo é o de sempre.
A raiz fictícia fica na pasta temporária, onde `decisao_da_cifra` fica em claro (como o WSL): a decisão de cifrar entra por
`cifra=` (o que a decisão do kit devolveria com a chave protegida). Chave de TESTE criada aqui; sem `gpg` 2.4, pula com o motivo.
Fundações fictícias em pastas descartáveis; nenhum dado real."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import KIT
from test_atualizar_fundacao_1710 import IDENTIDADE
from test_atualizar_fundacao_1710 import Fundacao as FundacaoBase

sys.path.insert(0, str(KIT / "tests"))
from apoio_cifra import CANARIO, LOOPBACK, chaveiros, exigir_gpg  # noqa: E402

from fundacao.core.backup_cifrado import MANIFESTO, verificar_cifrada  # noqa: E402
from fundacao.core.decifra_copia import desembrulhar  # noqa: E402

A = EXE = None


def setUpModule() -> None:
    global A, EXE
    EXE = exigir_gpg()
    A, = chaveiros("Teste A")  # apagada na saída do processo (apoio_cifra)


class Cifrada(FundacaoBase):
    def setUp(self):
        super().setUp()
        self.local = self.tmp / "local"
        self.cifra = {"modo": "cifrada", "chave": str(A.publica), "preparo_base": str(self.local), "sem_cifra": None}
        projeto = self.raiz / "projects" / "lab" / "data"
        projeto.mkdir(parents=True)
        (projeto / f"{CANARIO}.txt").write_text(f"conteudo fictício {CANARIO}\n", encoding="utf-8")

    def aplicar(self, **kw):
        kw.setdefault("cifra", self.cifra)
        with mock.patch.dict(os.environ, {IDENTIDADE: "titular-ensaio"}):
            return self.mod.aplicar(self.raiz, self.backups, "test_nenhum_*.py", prazo=900, **kw)

    def so_cifrada(self, pasta: Path) -> None:
        nomes = sorted(p.name for p in pasta.iterdir())
        self.assertIn(MANIFESTO, nomes)
        self.assertEqual([n for n in nomes if not (n.startswith("parte-") or n in (MANIFESTO, "LEIA-ME.txt"))], [], nomes)
        self.assertFalse((pasta / "manifest.json").exists())
        self.assertFalse((pasta / "files").exists())

    def bytes_de(self, pasta: Path) -> bytes:
        return b"".join(p.read_bytes() for p in sorted(pasta.rglob("*")) if p.is_file())


class TestAplicarCifrado(Cifrada):
    def test_n13_antes_e_depois_cifrados_e_o_ensaio_restaura_do_preparo_local(self):
        self.versao_antiga()
        no_ensaio = {}
        original = self.mod._ensaio

        def espiar(raiz, codigo, conferidos, antes, padrao, manter, pasta_base, prazo, limpeza):
            no_ensaio["pasta_base"] = pasta_base
            no_ensaio["antes_restaurado"] = antes
            no_ensaio["nas_copias"] = sorted(p.name for p in self.backups.iterdir())
            no_ensaio["claro_nas_copias"] = [p for p in self.backups.rglob("manifest.json")]
            no_ensaio["local_existia"] = Path(antes["pasta"]).is_dir()
            return original(raiz, codigo, conferidos, antes, padrao, manter, pasta_base, prazo, limpeza)

        with mock.patch.object(self.mod, "_ensaio", espiar):
            res = self.aplicar()
        reg = json.loads(Path(res["registro"]).read_text(encoding="utf-8"))
        # o ensaio restaurou a cópia EM CLARO do preparo local, num lugar local; o disco das cópias só tinha a ANTES cifrada
        self.assertTrue(Path(no_ensaio["pasta_base"]).samefile(self.local))
        self.assertTrue(no_ensaio["local_existia"])
        self.assertTrue(Path(no_ensaio["antes_restaurado"]["pasta"]).is_relative_to(self.local))
        self.assertEqual(no_ensaio["claro_nas_copias"], [], "raiz ou cópia em claro no disco das cópias durante o ensaio")
        self.assertEqual(len(no_ensaio["nas_copias"]), 1)
        self.assertTrue(no_ensaio["nas_copias"][0].startswith("antes-kit-"))
        ensaio = Path(reg["limpeza"]["pasta_do_ensaio"])
        self.assertTrue(ensaio.is_relative_to(self.local), ensaio)
        self.assertFalse(ensaio.is_relative_to(self.backups.resolve()))
        # as duas cópias são cifradas, sem nenhum texto em claro
        antes, depois = Path(reg["antes"]["pasta"]), Path(reg["depois"]["pasta"])
        self.assertEqual((antes.parent, depois.parent), (self.backups.resolve(), self.backups.resolve()))
        for pasta in (antes, depois):
            self.so_cifrada(pasta)
        todos = self.bytes_de(self.backups)
        self.assertNotIn(CANARIO.encode(), todos)
        self.assertNotIn(b"PRIVATE KEY BLOCK", todos)
        self.assertEqual(list(self.backups.glob("ensaio-atualizacao-*")), [])
        # o preparo local sai logo depois do ensaio, e o da DEPOIS pelo criar cifrado
        self.assertTrue(reg["limpeza"]["preparo_local"]["limpa"], reg["limpeza"])
        self.assertTrue(reg["limpeza"]["ensaio"]["limpa"], reg["limpeza"])
        self.assertEqual(list(self.local.iterdir()) if self.local.exists() else [], [])
        # âncoras: a do manifesto externo (a guardar) e a do conteúdo; destinatário certo; conferem sem senha
        for chave in ("antes", "depois"):
            r = reg[chave]
            self.assertTrue(r["cifrada"])
            self.assertEqual(r["destinatario"], A.impressao)
            v = verificar_cifrada(Path(r["pasta"]), sha256_manifesto=r["sha256_manifesto"],
                                  destinatario_esperado=A.impressao)
            self.assertTrue(v["ok"], v)
            self.assertEqual(v["sha256_manifesto_interno"], r["sha256_manifesto_interno"])
            self.assertNotEqual(r["sha256_manifesto"], r["sha256_manifesto_interno"])
        self.assertEqual(reg["antes"]["copia_local"]["sha256_manifesto"], reg["antes"]["sha256_manifesto_interno"])
        self.assertEqual(reg["cifra"]["modo"], "cifrada")
        # a ANTES abre com a chave de teste e é a fundação de antes (inclusive o arquivo de projeto)
        d = desembrulhar(antes, self.tmp / "antes-decifrada", A.casa, sha256_manifesto=reg["antes"]["sha256_manifesto"],
                         exe=EXE, extras_gpg=LOOPBACK)
        self.assertEqual(d["sha256_manifesto_interno"], reg["antes"]["sha256_manifesto_interno"])
        self.assertTrue((self.tmp / "antes-decifrada" / "files" / "projects" / "lab" / "data" / f"{CANARIO}.txt").is_file())
        self.assertTrue(any("CIFRADAS" in linha for linha in res["resumo"]), res["resumo"])
        self.assertFalse(self.trava.exists())

    def test_falha_no_ensaio_nao_deixa_a_copia_em_claro(self):
        self.versao_antiga()
        with mock.patch.object(self.mod, "_ensaio", side_effect=self.mod.Parada("ensaio", "falha simulada")):
            with self.assertRaises(self.mod.Parada) as e:
                self.aplicar()
        detalhes = e.exception.detalhes
        self.assertTrue(detalhes["limpeza"]["preparo_local"]["limpa"], detalhes["limpeza"])
        self.assertEqual(list(self.local.iterdir()) if self.local.exists() else [], [])
        copias = [p for p in self.backups.iterdir()]
        self.assertEqual(len(copias), 1)
        self.so_cifrada(copias[0])
        self.assertNotIn(CANARIO.encode(), self.bytes_de(self.backups))
        self.assertFalse(self.trava.exists())

    def test_falha_na_copia_cifrada_nao_promove_nada_e_a_raiz_fica(self):
        self.versao_antiga()
        antes = (self.raiz / "fundacao" / "__init__.py").read_bytes()
        with mock.patch.object(self.mod, "CIFRAR", "import sys\nsys.exit(3)\n"):
            with self.assertRaises(self.mod.Parada) as e:
                self.aplicar()
        self.assertEqual(e.exception.etapa, "backup")
        self.assertIn("nenhuma cópia cifrada foi promovida", e.exception.motivo)
        self.assertEqual((self.raiz / "fundacao" / "__init__.py").read_bytes(), antes, "a raiz foi alterada")
        self.assertEqual(list(self.backups.iterdir()) if self.backups.exists() else [], [])
        self.assertTrue(e.exception.detalhes["limpeza"]["preparo_local"]["limpa"])
        self.assertEqual(list(self.local.iterdir()) if self.local.exists() else [], [])


class TestOndeNasceOEnsaio(Cifrada):
    def test_padrao_local_com_a_chave_e_das_copias_sem_ela(self):
        com = self.mod._base_do_ensaio(self.raiz, self.backups, None, self.cifra)
        self.assertEqual(com, Path(os.path.abspath(self.local)))
        self.assertEqual(self.mod._base_do_ensaio(self.raiz, self.backups, None, {"modo": "claro"}), self.backups)
        self.assertEqual(self.mod._base_do_ensaio(self.raiz, self.backups, None), self.backups)
        outra = self.tmp / "outra"
        self.assertEqual(self.mod._base_do_ensaio(self.raiz, self.backups, outra, self.cifra), outra)
        self.assertEqual(self.mod._base_do_ensaio(self.raiz, self.backups, self.backups / "e", {"modo": "claro"}),
                         self.backups / "e", "sem a chave, o ensaio nas cópias de sempre continua valendo")

    def test_ensaio_no_disco_das_copias_recusa_com_a_chave_antes_de_qualquer_copia(self):
        for pasta in (self.backups, self.backups / "ensaio"):
            with self.subTest(pasta=str(pasta)):
                with mock.patch.object(self.mod, "_backup", side_effect=AssertionError("copiou")):
                    with self.assertRaises(self.mod.Parada) as e:
                        self.aplicar(pasta_ensaio=pasta)
                self.assertEqual(e.exception.etapa, "checar")
                self.assertIn("ficaria em claro", e.exception.motivo)
        self.assertFalse(self.backups.exists())
        self.assertFalse(self.local.exists())
        self.assertFalse(self.trava.exists())

    def test_preparo_local_dentro_da_raiz_ou_sobre_as_copias_recusa(self):
        casos = {"dentro da raiz": self.raiz / "evidence" / "local", "dentro das cópias": self.backups / "local",
                 "igual às cópias": self.backups, "sobre as cópias": self.tmp}
        for nome, base in casos.items():
            with self.subTest(nome):
                cifra = {**self.cifra, "preparo_base": str(base)}
                with self.assertRaises(self.mod.Parada) as e:
                    self.mod._base_do_ensaio(self.raiz, self.backups, None, cifra)
                self.assertEqual(e.exception.etapa, "checar")
                self.assertIn("preparo local", e.exception.motivo)


class TestDecisaoDaCifra(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("_atualizar_cifra",
                                                      Path(__file__).resolve().parents[1] / "atualizar_fundacao.py")
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self.raiz = Path(tempfile.mkdtemp(prefix="decisao-"))
        self.addCleanup(shutil.rmtree, self.raiz, ignore_errors=True)

    def test_raiz_de_ensaio_na_pasta_temporaria_fica_em_claro(self):
        self.assertEqual(self.mod.decisao_da_cifra(self.raiz)["modo"], "claro")

    def decidir(self, resposta):
        with mock.patch.object(self.mod, "em_pasta_temporaria", lambda _r: False), \
                mock.patch.object(self.mod, "rodar", return_value=resposta):
            return self.mod.decisao_da_cifra(self.raiz, "motivo")

    def test_recusa_e_saida_estranha_param_no_checar(self):
        with self.assertRaises(self.mod.Parada) as e:
            self.decidir((1, {"recusa": "a chave pública da cópia não está protegida"}, ""))
        self.assertEqual(e.exception.etapa, "checar")
        self.assertIn("não está protegida", e.exception.motivo)
        for ruim in ((1, None, "traceback"), (0, {"modo": "outro"}, ""), (0, None, "")):
            with self.subTest(ruim=ruim), self.assertRaises(self.mod.Parada):
                self.decidir(ruim)
        ok = self.decidir((0, {"modo": "cifrada", "chave": "C:/c.asc", "preparo_base": "C:/p"}, ""))
        self.assertEqual(ok["modo"], "cifrada")

    def test_o_programa_do_kit_com_sem_cifra_devolve_claro_e_o_motivo(self):
        """O programa DECIDIR de verdade (kit da skill, isolado): com --sem-cifra, claro (com o motivo, se há chave instalada)."""
        from codigo_conferido import python_isolado
        r = subprocess.run(python_isolado(KIT, self.mod.DECIDIR, "disco de ensaio fictício"), capture_output=True, text=True,
                           encoding="utf-8", timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        dados = json.loads(r.stdout)
        self.assertEqual(dados["modo"], "claro")
        self.assertIn(dados["sem_cifra"], (None, "disco de ensaio fictício"), "sem chave instalada o motivo não se aplica")
        self.assertTrue(dados["preparo_base"].endswith(os.path.join("FundacaoIA", "preparo-copias")))


if __name__ == "__main__":
    unittest.main()
