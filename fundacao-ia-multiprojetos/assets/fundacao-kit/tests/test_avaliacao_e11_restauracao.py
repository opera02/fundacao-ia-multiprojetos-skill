"""Avaliação E11 (21/10/2026), achado F-03: na restauração, o `component_id` de uma linha `component_disable` do
registro protegido virava nome de arquivo sem validação. Com `../`, a restauração liberava e desligava (`enabled:
false`) um JSON FORA da pasta de destino (sonda B da E11). Agora a linha com identificador fora do formato do registro
de componentes torna o registro ilegível (não libera, nada é copiado), a reaplicação monta o caminho por
`components.entry_path` (contido em registry/components/) e a recomposição pela trilha ignora id fora do formato.
"""

from __future__ import annotations

import json
import shutil

from helpers import FoundationTestCase

from fundacao.core import backup, components
from fundacao.core.contracts import ValidationError


class TestRestauracaoComIdForaDoFormato(FoundationTestCase):
    def setUp(self):
        super().setUp()
        self.log = self.root / "state" / "retiradas.jsonl"
        self.extra = []

    def tearDown(self):
        for p in self.extra:
            shutil.rmtree(p, ignore_errors=True)
        super().tearDown()

    def pasta(self, nome: str):
        p = self.root.parent / f"{self.root.name}-{nome}"
        self.extra.append(p)
        return p

    def linha_adulterada(self, component_id: str) -> None:
        linha = {"entity_type": "component_disable", "entity_id": "componente:vitima", "component_id": component_id,
                 "decided_by": "operador-lab", "decided_at": "2026-10-21T00:00:00Z"}
        with self.log.open("a", encoding="utf-8", newline="") as arq:
            arq.write(json.dumps(linha) + chr(10))

    def test_linha_que_sai_da_pasta_nao_libera_nem_altera_o_arquivo_de_fora(self):  # sonda B da E11
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "e11-f03")
        dest, fora = self.pasta("dest"), self.pasta("fora")
        fora.mkdir()
        vitima = fora / "vitima.json"
        vitima.write_text(json.dumps({"enabled": True, "observacao": "fora do destino"}), encoding="utf-8")
        antes = vitima.read_bytes()
        # dest/registry/components/../../../<fora>/vitima.json
        self.linha_adulterada("../../../" + fora.name + "/vitima")
        rep = backup.restore(snap, dest, self.log)
        self.assertFalse(rep["released"], rep)
        self.assertIn("ilegível", rep["reason"])
        self.assertEqual(vitima.read_bytes(), antes)
        self.assertFalse((fora / "vitima.tmp").exists())

    def test_cada_id_fora_do_formato_torna_o_registro_ilegivel(self):
        for ruim in ("../x", "a/b", "..", "C:/x", "x.json", "Maiuscula"):
            with self.subTest(component_id=ruim):
                texto = json.dumps({"entity_type": "component_disable", "entity_id": "componente:x",
                                    "component_id": ruim, "decided_by": "a", "decided_at": "2026-10-21"})
                with self.assertRaises(ValidationError):
                    backup._analisar_registro(texto, estrito=True)
        valido = json.dumps({"entity_type": "component_disable", "entity_id": "componente:source_manifest",
                             "component_id": "source_manifest", "decided_by": "a", "decided_at": "2026-10-21"})
        self.assertEqual(len(backup._analisar_registro(valido, estrito=True)[1]), 1)

    def test_desligamento_legitimo_continua_reaplicado(self):  # controle (TA-5)
        components.set_enabled(self.root, self.con, self.admin, "source_manifest", True)
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "e11-f03-controle")
        components.set_enabled(self.root, self.con, self.admin, "source_manifest", False)
        dest = self.pasta("dest")
        rep = backup.restore(snap, dest, self.log)
        self.assertTrue(rep["released"], rep)
        self.assertIn("componente:source_manifest", rep["reapplied"])
