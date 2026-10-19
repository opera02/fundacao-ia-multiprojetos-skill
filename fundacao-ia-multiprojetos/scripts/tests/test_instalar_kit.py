"""Auditoria externa da 1.3.4 — `instalar_kit.py`: contenção (F04) e instalação incompleta (F15).

Pastas descartáveis; o kit é copiado de `assets/fundacao-kit` desta skill. Nada é instalado no perfil.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from apoio import KIT, criar_ligacao_dir, rodar_script, versao_do_kit

PERSONALIZACAO = "# PERSONALIZACAO LOCAL FICTICIA\n"


def _arquivos(raiz: Path) -> dict[str, str]:
    return {p.relative_to(raiz).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(raiz.rglob("*")) if p.is_file()}


def _kit_esperado() -> dict[str, str]:
    return {k: v for k, v in _arquivos(KIT).items() if "__pycache__" not in k and not k.endswith(".pyc")}


class _Base(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="instalar-kit-teste-"))
        self.dest = self.base / "destino-autorizado"
        self.dest.mkdir()

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def instalar(self, *extra):
        p = rodar_script("instalar_kit.py", "--destino", self.dest, *extra)
        try:
            dados = json.loads(p.stdout)
        except json.JSONDecodeError:
            dados = None
        return p, dados


class TestF04ContencaoDoInstalador(_Base):
    def setUp(self):
        super().setUp()
        self.fora = self.base / "fora-do-destino"
        self.fora.mkdir()

    def _nada_escrito(self, *permitidos: str):
        self.assertEqual(sorted(p.relative_to(self.fora).as_posix() for p in self.fora.rglob("*")), [],
                         "o instalador escreveu fora do destino autorizado")
        self.assertEqual(sorted(p.name for p in self.dest.iterdir()), sorted(permitidos))

    def test_f04_pasta_fundacao_ligada_para_fora_e_recusada_sem_escrita(self):
        criar_ligacao_dir(self.dest / "fundacao", self.fora)
        p, _ = self.instalar()
        self.assertNotEqual(p.returncode, 0, p.stdout[-600:])
        self._nada_escrito("fundacao")

    def test_f04_subpasta_ligada_para_fora_e_recusada_sem_escrita(self):
        (self.dest / "fundacao").mkdir()
        criar_ligacao_dir(self.dest / "fundacao" / "core", self.fora)
        p, _ = self.instalar()
        self.assertNotEqual(p.returncode, 0, p.stdout[-600:])
        self.assertEqual(sorted(p.relative_to(self.fora).as_posix() for p in self.fora.rglob("*")), [])
        self.assertEqual(sorted(x.name for x in (self.dest / "fundacao").iterdir()), ["core"])
        self.assertEqual(sorted(x.name for x in self.dest.iterdir()), ["fundacao"])

    def test_f04_simulacao_tambem_aponta_a_ligacao(self):
        criar_ligacao_dir(self.dest / "registry", self.fora)
        p, dados = self.instalar("--simular")
        self.assertNotEqual(p.returncode, 0, p.stdout[-600:])
        self.assertTrue(dados and dados.get("recusado_por_contencao"), p.stdout[-600:])
        self._nada_escrito("registry")


class TestF15InstalacaoIncompleta(_Base):
    def _personalizar(self):
        alvo = self.dest / "fundacao" / "core" / "tasks.py"
        alvo.parent.mkdir(parents=True)
        alvo.write_text(PERSONALIZACAO, encoding="utf-8")
        return alvo

    def test_f15_conflito_nao_autorizado_nao_promove_nada_e_sai_com_codigo_nao_zero(self):
        alvo = self._personalizar()
        p, dados = self.instalar()
        self.assertNotEqual(p.returncode, 0, "instalação incompleta devolveu sucesso de processo")
        self.assertEqual(sorted(_arquivos(self.dest)), ["fundacao/core/tasks.py"],
                         "o conflito deixou uma instalação parcialmente promovida")
        self.assertEqual(alvo.read_text(encoding="utf-8"), PERSONALIZACAO)
        self.assertTrue(dados["atualizacao_incompleta"])
        self.assertIn("fundacao/core/tasks.py", dados["conflitos_preservados"])
        self.assertNotEqual(dados.get("composicao"), "verificada")
        self.assertIsNone(dados.get("kit_version"), "versão declarada sem composição verificada")

    def test_f15_repetir_e_previsivel_e_preserva_a_personalizacao(self):
        alvo = self._personalizar()
        p1, d1 = self.instalar()
        p2, d2 = self.instalar()
        self.assertEqual((p1.returncode, d1["conflitos_preservados"]), (p2.returncode, d2["conflitos_preservados"]))
        self.assertEqual(alvo.read_text(encoding="utf-8"), PERSONALIZACAO)
        self.assertEqual(sorted(_arquivos(self.dest)), ["fundacao/core/tasks.py"])

    def test_f15_instalacao_limpa_declara_a_composicao_verificada(self):
        p, dados = self.instalar()
        self.assertEqual(p.returncode, 0, p.stdout[-600:] + p.stderr[-600:])
        self.assertEqual(dados.get("composicao"), "verificada")
        self.assertEqual(dados.get("kit_version"), versao_do_kit(KIT))
        instalados = _arquivos(self.dest)
        for rel, h in _kit_esperado().items():
            self.assertEqual(instalados.get(rel), h, rel)

    def test_f15_atualizar_substitui_com_copia_anterior_e_verifica(self):
        self._personalizar()
        p, dados = self.instalar("--atualizar")
        self.assertEqual(p.returncode, 0, p.stdout[-600:] + p.stderr[-600:])
        self.assertEqual(dados.get("composicao"), "verificada")
        guardado = Path(dados["backup_dos_substituidos"]) / "fundacao" / "core" / "tasks.py"
        self.assertEqual(guardado.read_text(encoding="utf-8"), PERSONALIZACAO)
        self.assertEqual(_arquivos(self.dest)["fundacao/core/tasks.py"], _kit_esperado()["fundacao/core/tasks.py"])

    def test_f15_estado_misto_so_com_decisao_explicita_e_fica_registrado(self):
        alvo = self._personalizar()
        p, dados = self.instalar("--manter-conflitos")
        self.assertIsNotNone(dados, "a opção de estado misto explícito não existe: " + p.stderr[-300:])
        self.assertNotEqual(p.returncode, 0, "estado misto não é instalação completa")
        self.assertEqual(alvo.read_text(encoding="utf-8"), PERSONALIZACAO)
        self.assertEqual(dados.get("composicao"), "mista")
        self.assertIsNone(dados.get("kit_version"))
        registro = json.loads((self.dest / "registry" / "kit_install.json").read_text(encoding="utf-8"))
        self.assertEqual(registro[-1]["composicao"], "mista")
        self.assertIn("fundacao/core/tasks.py", registro[-1]["conflitos_preservados"])
        self.assertIn("fundacao/core/auth.py", _arquivos(self.dest))


class TestF15PromocaoDesfeita(_Base):
    """Complementar (caminho novo da 1.4.0): falha no meio da promoção desfaz o que foi promovido."""

    def test_f15_falha_na_promocao_desfaz_e_nao_declara_versao(self):
        import importlib.util
        from unittest import mock
        spec = importlib.util.spec_from_file_location("instalar_kit_em_teste", KIT.parents[1] / "scripts" / "instalar_kit.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        dest = self.dest.resolve()
        plano = mod.planejar(dest, False, "20261019T000000Z")
        self.assertTrue(plano["copiar"])
        original, chamadas = mod.os.replace, []

        def replace_que_falha(a, b):
            chamadas.append(b)
            if len(chamadas) == 5:
                raise OSError("falha fictícia no meio da promoção")
            return original(a, b)

        with mock.patch.object(mod.os, "replace", side_effect=replace_que_falha):
            backup, erros = mod.promover(dest, plano, "20261019T000000Z")
        self.assertTrue(erros)
        self.assertIsNone(backup)
        restantes = [p for p in self.dest.rglob("*") if p.is_file()]
        self.assertEqual(restantes, [], "a promoção falhou e deixou arquivos promovidos ou a preparação")


if __name__ == "__main__":
    unittest.main()
