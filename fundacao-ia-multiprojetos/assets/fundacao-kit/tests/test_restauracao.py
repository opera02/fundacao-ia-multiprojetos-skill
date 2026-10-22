"""A35 — restauração que falha fechada (R31, R44, R45, R56).

Registro de retiradas inexistente, de outra fundação, ilegível ou que não alcança a cópia não
libera (e registro ilegível não povoa o destino); memória retirada e acesso revogado depois da
cópia não reaparecem, e a reaplicação fica na trilha restaurada; a CLI restaura com o banco de
origem corrompido ou perdido, autorizada pela cópia ancorada (livro de cópias ao lado do registro),
sem criar nada na origem, inclusive com `#` no caminho e em pasta de rede (UNC); `init` numa fundação
antiga cria a identidade do registro e preenche as retiradas. A verificação confere o banco da cópia
contra o manifesto (hash e contagens), a cópia sai do modo WAL e componentes desligados depois da cópia
continuam desligados. A cópia é conferida pela âncora guardada fora dela (sha256_manifesto e livro de
cópias; varredura da 1.4.5, #8); sem âncora, só com a decisão motivada (auditoria da 1.7.6, #2).
"""

from __future__ import annotations

import gc
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path

from helpers import FoundationTestCase

from fundacao.core import backup
from fundacao.core.auth import Policy, resource_project
from fundacao.core.canon import sha256_text
from fundacao.core.db import connect
from fundacao.core.knowledge import KnowledgeService
from fundacao.core.memory import MemoryService

TEXTO = "A lista de anexos deve apresentar o nome, a versão e a origem."
RUBRICA = {k: {"resultado": "aprovado", "evidencia": "conferido"}
           for k in ("origem", "fidelidade", "vigencia", "acesso", "finalidade")}


class TestRestauracao(FoundationTestCase):
    def setUp(self):
        super().setUp()
        self.extra = []
        self.log = self.root / "state" / "retiradas.jsonl"

    def tearDown(self):
        for p in self.extra:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)  # arquivos soltos também (não deixar resto no TMPDIR)
        super().tearDown()

    def pasta(self, nome: str):
        p = self.root.parent / f"{self.root.name}-{nome}"
        self.extra.append(p)
        return p

    def publicar(self, sid: str):
        self.write_data("juridico-lab", "fontes/g.md", TEXTO)
        kj = KnowledgeService(self.root, self.con, self.jur)
        kr = KnowledgeService(self.root, self.con, self.revisor)
        kj.register_source("juridico-lab", sid, 1, "fontes/g.md")
        h = kj.prepare(sid, 1, [TEXTO])
        kj.index(sid, 1)
        kr.curate(sid, 1, RUBRICA, h, "2026-12-01", "lab")
        return kj, kr

    def memoria(self, corpo: str, op_id: str) -> str:
        mid = MemoryService(self.con, self.jur).propose(
            op_id=op_id, scope="project", project_id="juridico-lab", kind="fato", origin="humano",
            body=corpo, source_ref="FIC-ELIM")
        MemoryService(self.con, self.revisor).approve(mid, sha256_text(corpo))
        return mid

    def cli(self, principal: str | None, *args: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k != "FUNDACAO_PRINCIPAL"}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        if principal:
            env["FUNDACAO_PRINCIPAL"] = principal
        return subprocess.run([sys.executable, "-m", "fundacao", "--raiz", str(self.root), *args],
                              capture_output=True, text=True, encoding="utf-8", cwd=str(self.root), env=env)

    def eventos(self, raiz) -> list[dict]:
        con = connect(raiz / "state" / "state.sqlite")
        try:
            return [{"kind": r["kind"], "payload": json.loads(r["payload_json"])}
                    for r in con.execute("SELECT kind, payload_json FROM event ORDER BY seq")]
        finally:
            con.close()

    def test_registro_inexistente_nao_libera(self):
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "r1")
        res = backup.restore(snap, self.pasta("dest"), self.root / "state" / "caminho-errado.jsonl")
        self.assertFalse(res["released"])
        self.assertIn("inexistente", res["reason"])

    def test_registro_que_nao_alcanca_a_copia_nao_libera(self):
        kj, kr = self.publicar("juridico-lab/GUIA-002")
        kr.withdraw("juridico-lab/GUIA-002", 1, "retirada anterior à cópia")
        snap = self.pasta("snap")
        manifesto = backup.create_backup(self.root, snap, "r2")
        self.assertEqual(manifesto["retiradas"]["linhas"], 1)
        # Mesma identidade, mas só a linha de identidade: registro truncado.
        truncado = self.pasta("truncado.jsonl")
        truncado.write_text(self.log.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
        res = backup.restore(snap, self.pasta("dest"), truncado)
        self.assertFalse(res["released"])
        self.assertIn("não alcança", res["reason"])
        self.assertTrue(backup.restore(snap, self.pasta("dest2"), kj.tombstone_log)["released"])

    def test_copia_sem_retiradas_recusa_registro_qualquer(self):
        """NV-1: sem retiradas na cópia, um arquivo vazio ou o registro de outra fundação não liberam."""
        snap = self.pasta("snap")
        manifesto = backup.create_backup(self.root, snap, "r-nv1")
        self.assertEqual(manifesto["retiradas"]["linhas"], 0)
        self.assertTrue(manifesto["retiradas"]["log_id"].startswith("reg_"))
        vazio = self.pasta("vazio.jsonl")
        vazio.write_text("", encoding="utf-8")
        outra = self.pasta("outra-fundacao.jsonl")
        backup.ensure_tombstone_log(outra)
        for registro in (vazio, outra):
            res = backup.restore(snap, self.pasta(f"dest-{registro.stem}"), registro)
            self.assertFalse(res["released"], registro)
            self.assertIn("identidade diferente", res["reason"])
        self.assertTrue(backup.restore(snap, self.pasta("dest-ok"), self.log)["released"])

    def test_copia_de_kit_anterior_exige_aceitacao_explicita(self):
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "r-legado")
        mf = snap / "manifest.json"
        m = json.loads(mf.read_text(encoding="utf-8"))
        m["retiradas"] = {"linhas": 0, "ultima_sha256": None}  # formato da 1.2.0, sem identidade
        mf.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
        res = backup.restore(snap, self.pasta("dest"), self.log)
        self.assertFalse(res["released"])
        self.assertIn("kit anterior", res["reason"])
        dest = self.pasta("dest2")
        # O manifesto editado (como numa cópia antiga) também não consta no livro de cópias (#8).
        ok = backup.restore(snap, dest, self.log, aceitar_registro_nao_comprovado=True,
                            aceitar_copia_sem_ancora="cópia antiga conferida à mão (fictício)")
        self.assertTrue(ok["released"], ok)
        self.assertIn("decisão explícita", ok["ressalva"])
        fim = [e for e in self.eventos(dest) if e["kind"] == "restore_completed"]
        self.assertIn("decisão explícita", fim[-1]["payload"]["ressalva"])

    def test_memoria_retirada_depois_da_copia_nao_reaparece(self):
        corpo = "Preferência do cliente (FICTÍCIA) a eliminar"
        mid = self.memoria(corpo, "op-elim")
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "r3")
        MemoryService(self.con, self.revisor).withdraw(mid, "eliminação a pedido (fictício)")
        dest = self.pasta("dest")
        rep = backup.restore(snap, dest, self.log)
        self.assertTrue(rep["released"], rep)
        self.assertIn(mid, rep["reapplied"])
        con2 = connect(dest / "state" / "state.sqlite")
        try:
            estado = con2.execute("SELECT status FROM memory_item WHERE memory_id = ?", (mid,)).fetchone()[0]
            vistas = MemoryService(con2, self.jur).query(project_id="juridico-lab")
        finally:
            con2.close()
        self.assertEqual(estado, "withdrawn")
        self.assertNotIn(corpo, json.dumps(vistas, ensure_ascii=False))
        # NV-8: a reaplicação fica na trilha restaurada; o destino segue com o mesmo registro.
        reap = [e["payload"] for e in self.eventos(dest) if e["kind"] == "restore_reapplied"]
        self.assertIn(mid, [p["entidade"] for p in reap])
        self.assertEqual(backup.tombstone_state(dest / "state" / "retiradas.jsonl")["log_id"],
                         backup.tombstone_state(self.log)["log_id"])
        self.assertFalse((dest / "state" / backup.MARCA_NAO_LIBERADA).exists())
        self.assertNotIn("acao_necessaria", rep)  # mesmo kit: nada a atualizar
        self.assertNotIn("aviso_copia", rep)  # cópia nova: banco conferido também por hash

    def test_revogacao_posterior_a_copia_e_reaplicada(self):
        """NV-2: acesso revogado depois da cópia não volta; revogação anterior seguida de nova
        concessão (ambas antes da cópia) não é desfeita."""
        recurso = resource_project("juridico-lab")
        self.policy.register_principal(self.admin, "ex-colaborador")
        self.policy.grant(self.admin, "ex-colaborador", recurso, "read")
        self.policy.revoke(self.admin, "operador-juridico", recurso, "use")
        self.policy.grant(self.admin, "operador-juridico", recurso, "use")
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "r-nv2")
        self.policy.revoke(self.admin, "ex-colaborador", recurso, "read")
        dest = self.pasta("dest")
        rep = backup.restore(snap, dest, self.log)
        self.assertTrue(rep["released"], rep)
        self.assertEqual(rep["reapplied"], [f"acl:ex-colaborador:read:{recurso}"])
        con2 = connect(dest / "state" / "state.sqlite")
        try:
            pol = Policy(con2)
            self.assertFalse(pol.allowed("ex-colaborador", "read", recurso))
            self.assertTrue(pol.allowed("operador-juridico", "use", recurso))
        finally:
            con2.close()
        reap = [e["payload"] for e in self.eventos(dest) if e["kind"] == "restore_reapplied"]
        self.assertEqual([p["tipo"] for p in reap], ["acl_revoke"])

    def test_registro_malformado_nao_povoa_destino(self):
        """NV-10: o registro é lido e validado antes de copiar qualquer coisa."""
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "r-nv10")
        ruim = self.pasta("ruim.jsonl")
        ruim.write_text(self.log.read_text(encoding="utf-8") + "isto não é JSON\n", encoding="utf-8")
        dest = self.pasta("dest")
        res = backup.restore(snap, dest, ruim)
        self.assertFalse(res["released"])
        self.assertIn("ilegível (linha 2", res["reason"])
        self.assertFalse(dest.exists())

    def _restaurar_com_origem_danificada(self, dano: str):
        snap = self.pasta("snap")
        p = self.cli("operador-lab", "backup", "criar", "--destino", str(snap), "--rotulo", "r4")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.con.close()
        gc.collect()
        db = self.root / "state" / "state.sqlite"
        for extra in ("state.sqlite-wal", "state.sqlite-shm"):
            (self.root / "state" / extra).unlink(missing_ok=True)
        if dano == "corrompido":
            db.write_bytes(b"isto nao e um banco sqlite")
        else:
            db.unlink()
        negado = self.cli("operador-juridico", "backup", "restaurar", "--origem", str(snap),
                          "--destino", str(self.pasta("negado")), "--retiradas", str(self.log))
        self.assertEqual(negado.returncode, 2)
        self.assertIn("E_ACCESS_DENIED", negado.stderr)
        dest = self.pasta("dest")
        ok = self.cli("operador-lab", "backup", "restaurar", "--origem", str(snap), "--destino", str(dest),
                      "--retiradas", str(self.log))
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertTrue(json.loads(ok.stdout)["released"])
        return db

    def test_cli_restaura_com_banco_de_origem_corrompido(self):
        db = self._restaurar_com_origem_danificada("corrompido")
        self.assertEqual(db.read_bytes(), b"isto nao e um banco sqlite")  # origem intocada

    def test_cli_restaura_com_banco_de_origem_ausente(self):
        db = self._restaurar_com_origem_danificada("ausente")
        self.assertFalse(db.exists())  # nada foi criado na origem
        # NV-7: `status` na origem perdida recusa e também não cria banco.
        st = self.cli("operador-lab", "status")
        self.assertEqual(st.returncode, 2)
        self.assertIn("sem banco de estado", st.stderr)
        self.assertFalse(db.exists())

    def test_cli_backup_em_caminho_com_cerquilha(self):
        """RG-2: cópia em pasta com '#' (ex.: "Processo #12") verifica e restaura sem arquivo solto."""
        base = self.pasta("bk#1")
        snap = base / "snap"
        self.assertEqual(self.cli("operador-lab", "backup", "criar", "--destino", str(snap)).returncode, 0)
        ver = self.cli("operador-lab", "backup", "verificar", "--origem", str(snap))
        self.assertEqual(ver.returncode, 0, ver.stderr)
        self.assertTrue(json.loads(ver.stdout)["ok"])
        dest = self.pasta("dest#2")
        res = self.cli("operador-lab", "backup", "restaurar", "--origem", str(snap), "--destino", str(dest),
                       "--retiradas", str(self.log))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue(json.loads(res.stdout)["released"])
        solto = self.root.parent / f"{self.root.name}-bk"
        self.assertFalse(solto.exists(), "a URI cortada no '#' criaria este arquivo")

    def test_raiz_de_restauracao_nao_liberada_e_recusada(self):
        (self.root / "state" / backup.MARCA_NAO_LIBERADA).write_text("{}", encoding="utf-8")
        p = self.cli("operador-lab", "status")
        self.assertEqual(p.returncode, 2)
        self.assertIn("não liberada", p.stderr)

    def test_init_em_fundacao_antiga_cria_identidade_e_preenche(self):
        """RG-4: fundação de kit anterior (registro ausente ou sem as memórias) volta a restaurar."""
        mid = self.memoria("Memória retirada no kit antigo (fictícia)", "op-antiga")
        MemoryService(self.con, self.revisor).withdraw(mid, "retirada antiga")
        self.log.unlink()  # como numa fundação 1.1.0: a retirada de memória não foi registrada
        self.con.close()
        gc.collect()
        p = self.cli(None, "init")
        self.assertEqual(p.returncode, 0, p.stderr)
        saida = json.loads(p.stdout)["registro_retiradas"]
        self.assertTrue(saida["identidade"].startswith("reg_"))
        self.assertEqual(saida["preenchidas"], [mid])
        de_novo = json.loads(self.cli(None, "init").stdout)["registro_retiradas"]
        self.assertEqual(de_novo, {"identidade": saida["identidade"], "preenchidas": []})  # idempotente
        recs = backup.read_tombstone_log(self.log)
        self.assertEqual([(r["entity_type"], r["entity_id"], r["origem"]) for r in recs],
                         [("memory", mid, "preenchido-pelo-init")])
        self.con = connect(self.root / "state" / "state.sqlite")

    def test_banco_trocado_ou_esvaziado_na_copia_nao_confere(self):
        """TA-1 e TA-9: a cópia sai do WAL (conferir não cria -wal/-shm) e a verificação confere o banco
        contra o manifesto (hash e contagens): banco de outra fundação ou tabela esvaziada não liberam."""
        snap = self.pasta("snap")
        manifesto = backup.create_backup(self.root, snap, "r-ta1")
        db = snap / "state" / "state.sqlite"
        self.assertEqual(db.read_bytes()[18:20], bytes([1, 1]))  # cabeçalho: modo de diário clássico
        self.assertTrue(manifesto["db_sha256"])
        self.assertTrue(backup.verify_backup(snap)["ok"])
        self.assertEqual(sorted(p.name for p in db.parent.iterdir()), ["state.sqlite"])
        original = db.read_bytes()
        outra = self.pasta("outra") / "state.sqlite"
        connect(outra).close()  # banco íntegro de outra fundação (só o esquema)
        gc.collect()
        shutil.copy2(outra, db)
        trocado = backup.verify_backup(snap)
        self.assertFalse(trocado["ok"])
        self.assertIn("hash do banco diferente do manifesto", trocado["db_problemas"])
        dest = self.pasta("dest")
        self.assertFalse(backup.restore(snap, dest, self.log)["released"])
        self.assertFalse(dest.exists())
        db.write_bytes(original)
        con = sqlite3.connect(str(db))
        con.execute("DELETE FROM project")
        con.commit()
        con.close()
        m = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
        m["db_sha256"] = None  # como numa cópia anterior à 1.3.1: valem as contagens
        (snap / "manifest.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
        esvaziado = backup.verify_backup(snap)
        self.assertFalse(esvaziado["ok"])
        self.assertTrue(any("project" in p for p in esvaziado["db_problemas"]), esvaziado["db_problemas"])

    def test_cli_verificar_copia_alterada_sai_com_codigo_3(self):
        """TA-4: automação que confia no código de saída não aprova cópia alterada."""
        snap = self.pasta("snap")
        self.assertEqual(self.cli("operador-lab", "backup", "criar", "--destino", str(snap)).returncode, 0)
        (snap / "files" / "projects" / "juridico-lab" / "INSTRUCOES.md").write_text("alterado", encoding="utf-8")
        p = self.cli("operador-lab", "backup", "verificar", "--origem", str(snap))
        self.assertEqual(p.returncode, 3)
        self.assertFalse(json.loads(p.stdout)["ok"])

    def test_componente_desligado_depois_da_copia_continua_desligado(self):
        """TA-5: a desativação posterior à cópia é reaplicada; a resposta diz o que não é reaplicado."""
        from fundacao.core import components
        components.set_enabled(self.root, self.con, self.admin, "source_manifest", True)
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "r-ta5")
        components.set_enabled(self.root, self.con, self.admin, "source_manifest", False)
        dest = self.pasta("dest")
        rep = backup.restore(snap, dest, self.log)
        self.assertTrue(rep["released"], rep)
        self.assertIn("componente:source_manifest", rep["reapplied"])
        estado = json.loads((dest / "registry" / "components" / "source_manifest.json").read_text(encoding="utf-8"))
        self.assertFalse(estado["enabled"])
        self.assertTrue(any("route_policy" in x for x in rep["nao_reaplicado"]))

    def test_cli_criar_sem_destino_e_restaurar_em_pasta_vazia(self):
        """TA-6: erro dentro do contrato; pasta de destino existente e vazia serve para restaurar."""
        p = self.cli("operador-lab", "backup", "criar")
        self.assertEqual(p.returncode, 2)
        self.assertIn("--destino", json.loads(p.stderr)["error"]["message"])
        snap = self.pasta("snap")
        self.assertEqual(self.cli("operador-lab", "backup", "criar", "--destino", str(snap)).returncode, 0)
        vazia = self.pasta("vazia")
        vazia.mkdir()
        r = self.cli("operador-lab", "backup", "restaurar", "--origem", str(snap), "--destino", str(vazia),
                     "--retiradas", str(self.log))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(json.loads(r.stdout)["released"])

    @unittest.skipUnless(os.name == "nt", "caminho UNC só no Windows")
    def test_copia_em_pasta_de_rede(self):
        """TA-3: cópia numa pasta de rede (UNC) é criada, verificada e restaurada pela CLI."""
        bs = chr(92)
        local = self.pasta("rede #1").resolve()
        local.mkdir()
        unc = bs * 2 + "localhost" + bs + str(local)[0] + "$" + str(local)[2:]
        if not Path(unc).exists():
            self.skipTest("compartilhamento administrativo indisponível neste computador")
        snap = unc + bs + "snap"
        self.assertEqual(self.cli("operador-lab", "backup", "criar", "--destino", snap).returncode, 0)
        ver = self.cli("operador-lab", "backup", "verificar", "--origem", snap)
        self.assertEqual(ver.returncode, 0, ver.stderr)
        dest = self.pasta("dest-rede")
        res = self.cli("operador-lab", "backup", "restaurar", "--origem", snap, "--destino", str(dest),
                       "--retiradas", str(self.log))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue(json.loads(res.stdout)["released"])
        self.assertNotIn("aviso_destino", json.loads(res.stdout))  # destino local
        # O1: restaurar a fundação NUMA pasta de rede funciona para conferir, mas vem com aviso.
        dest_local = self.pasta("dest-em-rede").resolve()
        dest_unc = bs * 2 + "localhost" + bs + str(dest_local)[0] + "$" + str(dest_local)[2:]
        em_rede = self.cli("operador-lab", "backup", "restaurar", "--origem", snap, "--destino", dest_unc,
                           "--retiradas", str(self.log))
        self.assertEqual(em_rede.returncode, 0, em_rede.stderr)
        self.assertIn("disco local", json.loads(em_rede.stdout)["aviso_destino"])
        # Destino LOCAL escrito com o prefixo de caminho longo do Windows não é pasta de rede.
        dest_longo = bs * 2 + "?" + bs + str(self.pasta("dest-longo").resolve())
        longo = self.cli("operador-lab", "backup", "restaurar", "--origem", snap, "--destino", dest_longo,
                         "--retiradas", str(self.log))
        self.assertEqual(longo.returncode, 0, longo.stderr)
        self.assertNotIn("aviso_destino", json.loads(longo.stdout))

    def test_copia_com_kit_mais_antigo_pede_atualizacao(self):
        """N3: a raiz restaurada roda o kit que veio na cópia; a restauração avisa quando ele difere."""
        init = self.root / "fundacao" / "__init__.py"
        init.write_text(re.sub(r'KIT_VERSION = "[^"]+"', 'KIT_VERSION = "1.3.0"', init.read_text(encoding="utf-8")),
                        encoding="utf-8")
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "r-n3")
        rep = backup.restore(snap, self.pasta("dest"), self.log)
        self.assertTrue(rep["released"], rep)
        self.assertEqual(rep["kit_da_copia"], "1.3.0")
        self.assertIn("--atualizar", rep["acao_necessaria"])

    def test_copia_anterior_a_1_3_1_avisa_e_nao_cria_auxiliares(self):
        """N4: cópia sem db_sha256 (anterior à 1.3.1) é conferida só por integridade e contagens, com
        aviso; uma cópia antiga em WAL é lida sem criar -wal/-shm."""
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "r-n4")
        db = snap / "state" / "state.sqlite"
        con = sqlite3.connect(str(db))
        con.execute("PRAGMA journal_mode = WAL")  # como as cópias anteriores à 1.3.1
        con.close()
        gc.collect()
        for aux in ("-wal", "-shm"):
            Path(str(db) + aux).unlink(missing_ok=True)
        self.assertEqual(db.read_bytes()[18:20], bytes([2, 2]))
        m = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
        m.pop("db_sha256")
        (snap / "manifest.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
        ver = backup.verify_backup(snap)
        self.assertTrue(ver["ok"], ver)
        self.assertIn("só por integridade e contagens", ver["aviso"])
        self.assertEqual(sorted(p.name for p in db.parent.iterdir()), ["state.sqlite"])
        # Cópia antiga não consta no livro de cópias (#8): restaurá-la é decisão explícita.
        rep = backup.restore(snap, self.pasta("dest"), self.log, aceitar_copia_sem_ancora="cópia antiga (fictício)")
        self.assertTrue(rep["released"], rep)
        self.assertIn("contagens", rep["aviso_copia"])

    def test_manifesto_com_estrutura_invalida_fica_no_contrato(self):
        """N5: manifesto com JSON válido e estrutura errada sai com erro JSON e código 2."""
        snap = self.pasta("snap")
        self.assertEqual(self.cli("operador-lab", "backup", "criar", "--destino", str(snap)).returncode, 0)
        for conteudo in ("[]", "{}", '{"files": [1]}'):
            (snap / "manifest.json").write_text(conteudo, encoding="utf-8")
            p = self.cli("operador-lab", "backup", "verificar", "--origem", str(snap))
            self.assertEqual(p.returncode, 2, (conteudo, p.stderr))
            self.assertIn("manifesto", json.loads(p.stderr)["error"]["message"])

    def test_linha_de_tipo_novo_conta_no_backup_mas_a_restauracao_recusa(self):
        """Registro com tipo de linha de um kit mais novo: backup e init seguem (só contam a linha);
        a restauração não libera, porque não saberia reaplicá-la."""
        backup.append_tombstone_log(self.log, {"entity_type": "tipo_futuro", "entity_id": "futuro:1",
                                               "decided_by": "operador-lab", "decided_at": "2026-10-19T00:00:00Z"})
        snap = self.pasta("snap")
        manifesto = backup.create_backup(self.root, snap, "r-futuro")
        self.assertEqual(manifesto["retiradas"]["linhas"], 1)
        self.con.close()
        gc.collect()
        self.assertEqual(self.cli(None, "init").returncode, 0)
        self.con = connect(self.root / "state" / "state.sqlite")
        rep = backup.restore(snap, self.pasta("dest"), self.log)
        self.assertFalse(rep["released"])
        self.assertIn("tipo de linha desconhecido", rep["reason"])

    def test_arquivo_extra_na_copia_nao_confere(self):
        """N8: arquivo acrescentado à cópia (fora do manifesto), inclusive código em fundacao/, não confere
        e não é restaurado."""
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "r-n8")
        (snap / "files" / "fundacao" / "injetado.py").write_text("print('não devia estar aqui')\n", encoding="utf-8")
        ver = backup.verify_backup(snap)
        self.assertFalse(ver["ok"])
        self.assertEqual(ver["extras"], ["fundacao/injetado.py"])
        dest = self.pasta("dest")
        self.assertFalse(backup.restore(snap, dest, self.log)["released"])
        self.assertFalse(dest.exists())

    def test_metadados_do_sistema_na_copia_nao_barram_nem_voltam(self):
        """O8: Thumbs.db, desktop.ini e .DS_Store criados pelo sistema numa cópia guardada em pasta de rede
        não barram a restauração (ficam em `ignorados_do_so`) e não são restaurados."""
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "r-o8")
        (snap / "files" / "projects" / "juridico-lab" / "Thumbs.db").write_bytes(b"miniaturas")
        (snap / "files" / "desktop.ini").write_text("[.ShellClassInfo]\n", encoding="utf-8")
        (snap / "files" / "fundacao" / ".DS_Store").write_bytes(b"finder")
        ver = backup.verify_backup(snap)
        self.assertTrue(ver["ok"], ver)
        self.assertEqual(ver["extras"], [])
        self.assertEqual(sorted(ver["ignorados_do_so"]),
                         ["desktop.ini", "fundacao/.DS_Store", "projects/juridico-lab/Thumbs.db"])
        dest = self.pasta("dest")
        self.assertTrue(backup.restore(snap, dest, self.log)["released"])
        self.assertFalse((dest / "projects" / "juridico-lab" / "Thumbs.db").exists())
        self.assertFalse((dest / "desktop.ini").exists())

    def test_cli_ancora_da_copia(self):
        """#8 (varredura da 1.4.5): `backup criar` devolve a âncora (sha256_manifesto) e a anota no livro de
        cópias; `verificar` e `restaurar` conferem a cópia por ela; âncora errada sai com código 3 e nada é
        copiado; sem âncora e sem livro (só o registro guardado), a restauração não libera (código 3) — até a
        1.7.6 liberava com aviso (auditoria da 1.7.6, #2) — e, com `--aceitar-copia-sem-ancora "<motivo>"`,
        libera com aviso no stderr."""
        snap = self.pasta("snap")
        p = self.cli("operador-lab", "backup", "criar", "--destino", str(snap))
        self.assertEqual(p.returncode, 0, p.stderr)
        ancora = json.loads(p.stdout)["sha256_manifesto"]
        errada = "f" * 64
        ver = self.cli("operador-lab", "backup", "verificar", "--origem", str(snap), "--sha256-manifesto", errada)
        self.assertEqual(ver.returncode, 3, ver.stderr)
        self.assertEqual(json.loads(ver.stdout)["ancora"]["situacao"], "divergente")
        ver = self.cli("operador-lab", "backup", "verificar", "--origem", str(snap))
        self.assertEqual(ver.returncode, 0, ver.stderr)
        self.assertEqual(json.loads(ver.stdout)["ancora"]["situacao"], "conferida")  # pelo livro desta raiz
        dest = self.pasta("dest")
        r = self.cli("operador-lab", "backup", "restaurar", "--origem", str(snap), "--destino", str(dest),
                     "--retiradas", str(self.log), "--sha256-manifesto", errada)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertFalse(dest.exists())
        guardado = self.pasta("guardado")
        guardado.mkdir()
        shutil.copy2(self.log, guardado / "retiradas.jsonl")
        r = self.cli("operador-lab", "backup", "restaurar", "--origem", str(snap), "--destino", str(dest),
                     "--retiradas", str(guardado / "retiradas.jsonl"))
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertFalse(dest.exists())
        r = self.cli("operador-lab", "backup", "restaurar", "--origem", str(snap), "--destino", str(dest),
                     "--retiradas", str(guardado / "retiradas.jsonl"), "--aceitar-copia-sem-ancora",
                     "desastre: só o registro foi guardado (fictício)")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["ancora"]["situacao"], "ausente")
        self.assertIn("W_COPIA_SEM_ANCORA", r.stderr)
        r = self.cli("operador-lab", "backup", "restaurar", "--origem", str(snap), "--destino", str(self.pasta("dest2")),
                     "--retiradas", str(guardado / "retiradas.jsonl"), "--sha256-manifesto", ancora)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["ancora"]["situacao"], "conferida")

    def test_restaurar_sobre_a_origem_e_erro_do_contrato(self):
        snap = self.pasta("snap")
        self.assertEqual(self.cli("operador-lab", "backup", "criar", "--destino", str(snap)).returncode, 0)
        p = self.cli("operador-lab", "backup", "restaurar", "--origem", str(snap), "--destino", str(self.root),
                     "--retiradas", str(self.log))
        self.assertEqual(p.returncode, 2)
        self.assertEqual(json.loads(p.stderr)["error"]["code"], "E_ARQUIVO")


if __name__ == "__main__":
    unittest.main()
