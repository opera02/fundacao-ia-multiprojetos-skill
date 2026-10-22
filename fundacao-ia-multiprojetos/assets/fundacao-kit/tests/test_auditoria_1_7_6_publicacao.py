"""Auditoria Codex Security da 1.7.6, #11: arquivos de publicação com nome previsível seguiam ligação plantada.

O temporário da saída e o do recibo de uma etapa (`<saida>.tmp`, `<saida>.receipt.tmp`), o do registro de componentes
(`registry/components/<id>.tmp`) e o registro de decisões (`decisoes/registro.jsonl`, aberto para acrescentar) tinham
nome previsível e eram abertos com `open` comum. Uma ligação plantada ali fazia a fundação gravar no arquivo de fora —
aqui, um arquivo de OUTRO projeto. No Windows, sem privilégio, o caminho é o vínculo físico (hard link, `mklink /H`):
o link simbólico de arquivo entra só onde o sistema deixa criar, e a junção (`mklink /J`) vale para pasta.
Agora tudo passa por `core/publicacao.py`: temporário imprevisível e exclusivo, `fsync` e `os.replace`; destino que é
ligação ou pasta é recusado; o registro de decisões recusa ligação e vínculo físico ANTES de gravar a trilha.
Os testes de regressão falham no kit 1.7.6 (a saída fica no relatório da 1.7.7); os da primitiva importam o módulo
novo dentro do teste. Dados e identidades fictícios.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import CANARIOS, FoundationTestCase
from apoio_auditoria import criar_ligacao_dir, trocar_pasta_por_ligacao
from test_decisoes_cli import DecisoesCliCase

from fundacao.core import components, decisoes
from fundacao.core.contracts import PathEscape
from fundacao.core.tasks import Coordinator, StepDef


def tipos_de_ligacao(base: Path) -> list[str]:
    """Ligações de ARQUIVO que este sistema deixa criar sem privilégio: o vínculo físico (NTFS, ext4) sempre; o link
    simbólico onde houver permissão (no Windows, modo de desenvolvedor ou administrador)."""
    tipos, alvo = [], base / ".sonda-alvo"
    alvo.write_bytes(b"")
    for tipo, criar in (("vinculo-fisico", os.link), ("link-simbolico", os.symlink)):
        link = base / f".sonda-{tipo}"
        try:
            criar(alvo, link)
            tipos.append(tipo)
        except (OSError, NotImplementedError):
            pass
        finally:
            if os.path.lexists(link):
                os.unlink(link)
    alvo.unlink()
    if not tipos:
        raise unittest.SkipTest("nem vínculo físico nem link simbólico de arquivo neste sistema de arquivos")
    return tipos


def ligar(link: Path, alvo: Path, tipo: str) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    (os.link if tipo == "vinculo-fisico" else os.symlink)(alvo, link)


class TestTemporariosDaPublicacao(FoundationTestCase):
    def setUp(self):
        super().setUp()
        self.tipos = tipos_de_ligacao(self.root)

    def nova_execucao(self):
        coord = Coordinator(self.root, self.con, self.jur, "juridico-lab")
        return coord, coord.start_run(coord.create_task("publicação (fictícia)"), "publicacao", "1", [StepDef("a")])

    def saida_da_geracao(self, ctx) -> Path:
        """Nome da saída que a etapa vai publicar: quem lê o projeto o calcula (o hash das entradas aparece no status)."""
        ih = self.con.execute("SELECT input_hash FROM step WHERE run_id = ? AND step_id = ?",
                              (ctx.run_id, ctx.step_id)).fetchone()[0]
        return ctx._coordinator._output_path(ctx.run_id, ctx.step_id, ih, ctx._execution)

    def test_saida_e_recibo_nao_seguem_ligacao_plantada_no_temporario(self):
        for tipo in self.tipos:
            with self.subTest(tipo=tipo):
                vitimas = {sufixo: self.write_data("reversa-lab", f"docs/vitima-{tipo}{sufixo}.md",
                                                   f"Especificação {CANARIOS['reversa-lab']} {sufixo}")
                           for sufixo in (".tmp", ".receipt.tmp")}
                antes = {s: p.read_bytes() for s, p in vitimas.items()}
                coord, run = self.nova_execucao()

                def etapa(ctx):
                    saida = self.saida_da_geracao(ctx)
                    for sufixo, vitima in vitimas.items():  # quem opera o projeto planta as ligações
                        ligar(saida.with_suffix(sufixo), vitima, tipo)
                    return "SAIDA-FICTICIA"

                res = coord.run(run, {"a": etapa})
                self.assertEqual({s: p.read_bytes() for s, p in vitimas.items()}, antes,
                                 "a publicação gravou no arquivo de outro projeto pela ligação")
                self.assertEqual(res["state"], "succeeded")
                self.assertEqual((self.root / res["steps"][0]["output_ref"]).read_bytes(), b"SAIDA-FICTICIA")

    def test_saida_que_virou_juncao_e_recusada_sem_gravar(self):
        alvo = self.root / "projects" / "reversa-lab" / "outputs"
        antes = sorted(p.name for p in alvo.rglob("*"))
        coord, run = self.nova_execucao()
        pasta = []

        def etapa(ctx):
            saida = self.saida_da_geracao(ctx)
            saida.parent.mkdir(parents=True, exist_ok=True)
            criar_ligacao_dir(saida, alvo)  # o nome final da saída vira junção (link simbólico fora do Windows)
            pasta.append(saida.parent)
            return "SAIDA-FICTICIA"

        with self.assertRaises(PathEscape):
            coord.run(run, {"a": etapa})
        self.assertEqual(sorted(p.name for p in alvo.rglob("*")), antes, "a publicação gravou na pasta de outro projeto")
        self.assertEqual([p.name for p in pasta[0].iterdir() if p.name.endswith(".tmp")], [],
                         "a recusa deixou temporário para trás")

    def test_registro_de_componente_nao_segue_ligacao_plantada_no_temporario(self):
        reg = self.root / "registry" / "components"
        for tipo in self.tipos:
            with self.subTest(tipo=tipo):
                vitima = self.write_data("reversa-lab", f"catalogo-{tipo}.json", '{"doc-caixasim-01": "docs/x.md"}')
                antes = vitima.read_bytes()
                ligar(reg / "source_manifest.tmp", vitima, tipo)
                components.set_enabled(self.root, self.con, self.admin, "source_manifest", True)
                self.assertEqual(vitima.read_bytes(), antes, "habilitar gravou no arquivo de outro projeto")
                self.assertTrue(components.load_entry(self.root, "source_manifest")["enabled"])
                (reg / "source_manifest.tmp").unlink()
                components.set_enabled(self.root, self.con, self.admin, "source_manifest", False)

    def test_arquivo_do_registro_de_componente_que_e_ligacao(self):  # controle: passa antes e depois
        """Link simbólico no próprio `<id>.json` para fora de `registry/components`: a contenção do registro
        (`entry_path`) já o recusava antes de qualquer efeito. Vínculo físico: `os.replace` troca o nome e o outro
        vínculo fica como estava."""
        arquivo = self.root / "registry" / "components" / "source_manifest.json"
        original = arquivo.read_bytes()
        for tipo in self.tipos:
            with self.subTest(tipo=tipo):
                vitima = self.root / "projects" / "reversa-lab" / "data" / f"entrada-{tipo}.json"
                vitima.write_bytes(original)  # o alvo precisa parecer um registro válido para ser lido
                arquivo.unlink()
                ligar(arquivo, vitima, tipo)
                eventos = self.con.execute("SELECT COUNT(*) FROM event").fetchone()[0]
                if tipo == "link-simbolico":
                    with self.assertRaises(PathEscape):
                        components.set_enabled(self.root, self.con, self.admin, "source_manifest", True)
                    self.assertEqual(self.con.execute("SELECT COUNT(*) FROM event").fetchone()[0], eventos,
                                     "a habilitação registrou evento antes de recusar")
                else:
                    components.set_enabled(self.root, self.con, self.admin, "source_manifest", True)
                    self.assertTrue(components.load_entry(self.root, "source_manifest")["enabled"])
                self.assertEqual(vitima.read_bytes(), original, "habilitar gravou no alvo da ligação")
                arquivo.unlink()
                arquivo.write_bytes(original)


class TestRegistroDeDecisoes(DecisoesCliCase):
    def setUp(self):
        super().setUp()
        self.tipos = tipos_de_ligacao(self.root)
        self.reg = self.pasta / "decisoes" / "registro.jsonl"
        # Vítima: o registro de decisões de OUTRO projeto (no mesmo volume, como o vínculo físico exige).
        self.vitima = self.root / "projects" / "reversa-lab" / "decisoes" / "registro.jsonl"
        self.vitima.parent.mkdir(parents=True, exist_ok=True)
        self.vitima.write_text('{"decisao_id": "dec-alheia-ficticia", "tipo": "aceite"}\n', encoding="utf-8")
        self.antes = self.vitima.read_bytes()

    def registrar(self, arq: Path) -> tuple[int, dict | None, str]:
        return self.cli("operador-lab", "decisao", "registrar", "--arquivo", str(arq))

    def assinada(self) -> Path:
        arq = self.preparada()
        self.chaves.assinar(arq)
        return arq

    def test_registro_com_ligacao_e_recusado_antes_de_gravar_a_trilha(self):
        for tipo in self.tipos:
            with self.subTest(tipo=tipo):
                arq = self.assinada()
                ligar(self.reg, self.vitima, tipo)
                codigo, r, erro = self.registrar(arq)
                self.assertEqual(codigo, 2, (r, erro))
                self.assertIn("E_PATH_ESCAPE", erro)
                self.assertEqual(self.vitima.read_bytes(), self.antes, "a decisão foi parar no registro de outro projeto")
                self.assertEqual(self.eventos(decisoes.EVENTO_ASSINADA), 0, "a trilha recebeu a decisão antes da recusa")
                self.reg.unlink()

    def test_registro_que_e_juncao_e_recusado_antes_de_gravar_a_trilha(self):
        arq = self.assinada()
        self.reg.parent.mkdir(parents=True, exist_ok=True)
        criar_ligacao_dir(self.reg, self.vitima.parent)
        codigo, r, erro = self.registrar(arq)
        self.assertEqual(codigo, 2, (r, erro))
        self.assertIn("E_PATH_ESCAPE", erro)
        self.assertEqual(self.eventos(decisoes.EVENTO_ASSINADA), 0, "metade registrada: trilha sem a linha")
        self.assertEqual(self.vitima.read_bytes(), self.antes)

    def test_pasta_de_decisoes_trocada_por_juncao_depois_da_conferencia(self):
        arq = self.assinada()
        v = decisoes.verificar_decisao(arq, self.pasta, self.chaves.ancora)
        self.assertTrue(v["valida"], v)
        trocar_pasta_por_ligacao(self.pasta / "decisoes", self.vitima.parent)  # corrida: troca depois de conferir
        with self.assertRaises(PathEscape):
            decisoes.registrar_decisao(self.con, self.admin, self.pasta, v)
        self.assertEqual(self.vitima.read_bytes(), self.antes, "a decisão foi parar no registro de outro projeto")
        self.assertEqual(self.eventos(decisoes.EVENTO_ASSINADA), 0)


class TestPrimitivaDePublicacao(unittest.TestCase):
    """A primitiva (core/publicacao.py, novo na 1.7.7) contra as trocas que o nome previsível permitia."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="fundacao-publicacao-"))
        self.tipos = tipos_de_ligacao(self.base)

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def test_registro_trocado_entre_a_conferencia_e_a_abertura_e_recusado(self):
        from fundacao.core import publicacao
        reg, vitima = self.base / "registro.jsonl", self.base / "vitima.jsonl"
        for tipo in self.tipos:
            with self.subTest(tipo=tipo):
                reg.write_bytes(b'{"linha": 1}\n')
                vitima.write_bytes(b'{"vitima": true}\n')
                abrir = os.open

                def trocar_e_abrir(caminho, *args, **kwargs):
                    if Path(caminho) == reg:  # entre a conferência (lstat) e a abertura
                        reg.unlink()
                        ligar(reg, vitima, tipo)
                    return abrir(caminho, *args, **kwargs)

                with mock.patch.object(publicacao.os, "open", side_effect=trocar_e_abrir):
                    with self.assertRaises(PathEscape):
                        publicacao.anexar(reg, b'{"linha": 2}\n')
                self.assertEqual(vitima.read_bytes(), b'{"vitima": true}\n')
                reg.unlink()

    def test_publicar_troca_o_nome_sem_gravar_atraves_do_vinculo(self):
        from fundacao.core import publicacao
        destino, outro_nome = self.base / "saida.out", self.base / "outro-nome.txt"
        outro_nome.write_bytes(b"ORIGINAL")
        os.link(outro_nome, destino)
        publicacao.publicar(destino, b"NOVO")
        self.assertEqual((destino.read_bytes(), outro_nome.read_bytes()), (b"NOVO", b"ORIGINAL"))
        self.assertEqual(sorted(p.name for p in self.base.iterdir() if not p.name.startswith(".sonda")),
                         ["outro-nome.txt", "saida.out"], "temporário ficou para trás")

    def test_anexar_cria_o_registro_e_acrescenta_em_lf(self):
        from fundacao.core import publicacao
        reg = self.base / "decisoes" / "registro.jsonl"
        reg.parent.mkdir()
        publicacao.anexar(reg, b'{"linha": 1}\n')
        publicacao.anexar(reg, b'{"linha": 2}\n')
        self.assertEqual(reg.read_bytes(), b'{"linha": 1}\n{"linha": 2}\n')
        os.link(reg, self.base / "outro-vinculo.jsonl")
        with self.assertRaises(PathEscape):
            publicacao.anexar(reg, b'{"linha": 3}\n')
        self.assertEqual(reg.read_bytes(), b'{"linha": 1}\n{"linha": 2}\n')


if __name__ == "__main__":
    unittest.main()
