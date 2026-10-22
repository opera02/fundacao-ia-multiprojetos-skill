"""Revisão de segurança da 1.7.7 (diferença f1b7a19..f1bdc88), área do kit: os resíduos apontados no HEAD revisado
(f1bdc88). Cada teste exige o comportamento seguro e falhava ali por asserção (a saída fica no relatório da revisão).
Identidades, projetos e conteúdos são fictícios; nada é executado do código da cópia.

R177-KIT-01: o livro de cópias (`state/copias.jsonl`) não é âncora externa no perfil de dados reais do WSL, em que a
sessão grava `state/` e a pasta de backups: cópia alterada depois do `backup criar` e entrada nova no livro eram
liberadas como "conferida", sem aviso; registro e livro DENTRO da própria cópia também liberavam e, sem fundação viva,
autorizavam. Agora livro e registro dentro de `--origem` não valem (o motivo vai na resposta), e a âncora vinda do
livro traz `aviso_ancora` com o limite dele.
R177-KIT-02: qualquer `--raiz` com banco legível era a "fundação viva", até a própria cópia; agora a raiz igual à
cópia, dentro dela ou com o manifesto de uma cópia não vale, e `autorizacao` mostra a raiz resolvida. Rodando fora da
raiz, a negativa lembra o `--raiz` (antes, só pedia o `--sha256-manifesto`, como num desastre).
R177-KIT-03: `backup verificar` no lugar calculava o hash pelo nome, através de junção dentro de `files/`; agora lista
antes, sem seguir ligação, e só calcula o hash do arquivo comum listado, preso ao objeto da listagem.
R177-KIT-04: o livro de cópias, o registro protegido e a exportação de eventos acresciam com `open("a")`, que segue
vínculo físico e ligação até um arquivo de fora; agora passam por `publicacao.anexar`, que recusa sem gravar.
R177-KIT-05: o destino vazio criado antes era trocado pela pasta preparada, e as permissões dele sumiam sem aviso;
agora a resposta avisa e manda proteger a pasta de cima do destino (a promoção continua atômica).
"""

from __future__ import annotations

import gc
import io
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from apoio_auditoria import trocar_pasta_por_ligacao
from test_auditoria_1_7_6_publicacao import ligar, tipos_de_ligacao
from test_auditoria_1_7_7_ancora import MOTIVO, _Base, sha256_de

from fundacao.core import backup, events
from fundacao.core.auth import resource_project
from fundacao.core.contracts import FundacaoError


class _Revisao(_Base):
    def cli_em(self, principal: str | None, raiz: Path | None, cwd: Path, *args: str) -> subprocess.CompletedProcess:
        """CLI com `--raiz` explícita ou, sem ela, a pasta de trabalho (`cwd`) como raiz, como roda o titular."""
        env = {k: v for k, v in os.environ.items() if k != "FUNDACAO_PRINCIPAL"}
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(self.root))  # o kit, de qualquer pasta de trabalho
        if principal:
            env["FUNDACAO_PRINCIPAL"] = principal
        return subprocess.run([sys.executable, "-m", "fundacao", *(["--raiz", str(raiz)] if raiz else []), *args],
                              capture_output=True, text=True, encoding="utf-8", cwd=str(cwd), env=env)

    def criar_copia(self, nome: str = "snap") -> tuple[Path, str]:
        snap = self.pasta(nome)
        p = self.cli("operador-lab", "backup", "criar", "--destino", str(snap))
        self.assertEqual(p.returncode, 0, p.stderr)
        return snap, json.loads(p.stdout)["sha256_manifesto"]

    def plantar_na_copia(self, snap: Path) -> Path:
        """Variante circular: registro e livro DENTRO da própria cópia, o livro com a âncora do manifesto dela."""
        (snap / "state" / "retiradas.jsonl").write_bytes(self.log.read_bytes())
        (snap / "state" / backup.LIVRO_COPIAS).write_text(json.dumps(
            {"rotulo": "plantado (fictício)", "sha256_manifesto": sha256_de(snap / "manifest.json")}) + "\n",
            encoding="utf-8")
        return snap / "state" / "retiradas.jsonl"

    def perder_a_fundacao_viva(self) -> None:
        self.con.close()
        gc.collect()
        for nome in ("state.sqlite", "state.sqlite-wal", "state.sqlite-shm"):
            (self.root / "state" / nome).unlink(missing_ok=True)


class TestKit01LivroNaoEAncoraExterna(_Revisao):
    def test_kit01_registro_e_livro_dentro_da_copia_nao_liberam(self):
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "r177-circular")
        self.forjar_admin(snap, "operador-juridico")
        registro = self.plantar_na_copia(snap)
        dest = self.pasta("dest")
        res = backup.restore(snap, dest, registro)
        self.assertFalse(res["released"], "registro e livro dentro da própria cópia liberaram a restauração")
        self.assertIn("dentro da própria cópia", res["reason"])
        self.assertFalse(dest.exists(), "nada pode ser copiado para o destino")
        # Registro guardado fora, livro informado dentro da cópia: o livro não vale (ausente, com o motivo).
        res = backup.restore(snap, dest, self.log, livro=snap / "state" / backup.LIVRO_COPIAS)
        self.assertFalse(res["released"], res)
        self.assertEqual(res["check"]["ancora"]["situacao"], "ausente")
        self.assertIn("dentro da própria cópia", res["reason"])
        self.assertFalse(dest.exists())
        ver = backup.verify_backup(snap, livro=snap / "state" / backup.LIVRO_COPIAS)
        self.assertEqual(ver["ancora"]["situacao"], "ausente")
        self.assertIn("dentro da própria cópia", ver["ancora"].get("livro_recusado", ""))

    def test_kit01_sem_fundacao_viva_livro_dentro_da_copia_nao_autoriza(self):
        snap, _ = self.criar_copia()
        self.forjar_admin(snap, "operador-juridico")  # quem não administra a fundação forja a ACL na cópia
        registro = self.plantar_na_copia(snap)
        self.perder_a_fundacao_viva()
        dest = self.pasta("dest")
        p = self.cli("operador-juridico", "backup", "restaurar", "--origem", str(snap), "--destino", str(dest),
                     "--retiradas", str(registro), "--aceitar-copia-sem-ancora", MOTIVO)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("E_ACCESS_DENIED", p.stderr)
        self.assertIn("dentro da própria cópia", p.stderr)
        self.assertFalse(dest.exists())

    def test_kit01_ancora_pelo_livro_avisa_e_o_sha256_guardado_fora_recusa(self):
        """O que a revisão reproduziu: cópia alterada depois do `backup criar` e entrada nova no livro (quem grava
        `state/` e a pasta de backups faz as duas). O livro não distingue isso: pelo livro, a restauração continua
        liberada (limite declarado), mas avisa, também no stderr; o sha256_manifesto guardado fora recusa."""
        snap = self.pasta("snap")
        original = backup.create_backup(self.root, snap, "r177-livro")["sha256_manifesto"]
        self.forjar_admin(snap, "operador-juridico")
        livro = self.root / "state" / backup.LIVRO_COPIAS
        with open(livro, "a", encoding="utf-8", newline="\n") as fh:  # o atacante não usa o kit
            fh.write(json.dumps({"rotulo": "acrescentada (fictícia)",
                                 "sha256_manifesto": sha256_de(snap / "manifest.json")}) + "\n")
        ver = backup.verify_backup(snap, livro=livro)
        self.assertEqual(ver["ancora"]["situacao"], "conferida")
        self.assertIn("aviso_ancora", ver, "a âncora vinda do livro foi aceita sem aviso")
        self.assertIn("state/", ver["aviso_ancora"])
        self.assertIn("--sha256-manifesto", ver["aviso_ancora"])
        dest = self.pasta("dest")
        res = backup.restore(snap, dest, self.log)
        self.assertTrue(res["released"], res)  # limite: o livro só vale tanto quanto state/ está protegido
        self.assertEqual(res["ancora"].get("fonte"), "livro de cópias")
        self.assertIn("WSL", res.get("aviso_ancora", ""))
        recusa = self.pasta("dest-sha")
        res = backup.restore(snap, recusa, self.log, sha256_manifesto=original)
        self.assertFalse(res["released"])
        self.assertEqual(res["check"]["ancora"]["situacao"], "divergente")
        self.assertFalse(recusa.exists())
        informada = backup.verify_backup(snap, sha256_manifesto=sha256_de(snap / "manifest.json"), livro=livro)
        self.assertNotIn("aviso_ancora", informada)  # a âncora informada não depende de state/
        cli = self.cli("operador-lab", "backup", "restaurar", "--origem", str(snap), "--destino",
                       str(self.pasta("dest-cli")), "--retiradas", str(self.log))
        self.assertEqual(cli.returncode, 0, cli.stderr)
        self.assertIn("W_ANCORA_DO_LIVRO", cli.stderr)
        self.assertNotIn("W_COPIA_SEM_ANCORA", cli.stderr)


class TestKit02RaizQueEACopia(_Revisao):
    def test_kit02_a_propria_copia_nao_e_fundacao_viva(self):
        snap, _ = self.criar_copia()
        self.forjar_admin(snap, "operador-juridico")  # não administra a fundação viva; forja a ACL na cópia
        registro = self.registro_guardado_sem_livro()
        dentro = snap / "files"
        casos = (("--raiz <cópia>", snap, self.root), ("rodando de dentro da cópia", None, snap),
                 ("--raiz dentro da cópia", dentro, self.root))
        for n, (nome, raiz, cwd) in enumerate(casos):
            with self.subTest(nome):
                if raiz == dentro:  # banco forjado plantado dentro de files/
                    (dentro / "state").mkdir()
                    shutil.copy2(snap / "state" / "state.sqlite", dentro / "state" / "state.sqlite")
                dest = self.pasta(f"dest-{n}")
                ver = self.cli_em("operador-juridico", raiz, cwd, "backup", "verificar", "--origem", str(snap))
                self.assertEqual(ver.returncode, 2, ver.stdout + ver.stderr)
                self.assertIn("E_ACCESS_DENIED", ver.stderr)
                rest = self.cli_em("operador-juridico", raiz, cwd, "backup", "restaurar", "--origem", str(snap),
                                   "--destino", str(dest), "--retiradas", str(registro),
                                   "--aceitar-copia-sem-ancora", MOTIVO)
                self.assertEqual(rest.returncode, 2, rest.stdout + rest.stderr)
                self.assertIn("E_ACCESS_DENIED", rest.stderr)
                self.assertFalse(dest.exists())

    def test_kit02_raiz_com_manifesto_de_copia_nao_e_fundacao_viva(self):
        snap, _ = self.criar_copia()
        outra, _ = self.criar_copia("outra-copia")  # outra cópia, com a ACL forjada, usada como --raiz
        self.forjar_admin(outra, "operador-juridico")
        registro = self.registro_guardado_sem_livro()
        dest = self.pasta("dest")
        p = self.cli_em("operador-juridico", outra, self.root, "backup", "restaurar", "--origem", str(snap),
                        "--destino", str(dest), "--retiradas", str(registro), "--aceitar-copia-sem-ancora", MOTIVO)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("E_ACCESS_DENIED", p.stderr)
        self.assertIn("manifest.json", p.stderr)
        self.assertFalse(dest.exists())

    def test_kit02_fundacao_viva_real_continua_decidindo_e_mostra_a_raiz(self):
        snap, _ = self.criar_copia()
        dest = self.pasta("dest")
        p = self.cli("operador-lab", "backup", "restaurar", "--origem", str(snap), "--destino", str(dest),
                     "--retiradas", str(self.log))
        self.assertEqual(p.returncode, 0, p.stderr)
        saida = json.loads(p.stdout)
        self.assertTrue(saida["released"])
        self.assertEqual(saida["autorizacao"]["politica"], "fundação viva")
        self.assertIn("raiz", saida["autorizacao"], "a autorização não mostra a raiz que decidiu")
        self.assertEqual(Path(saida["autorizacao"]["raiz"]), self.root.resolve())
        ver = self.cli("operador-lab", "backup", "verificar", "--origem", str(snap))
        self.assertEqual(ver.returncode, 0, ver.stderr)
        self.assertEqual(Path(json.loads(ver.stdout)["autorizacao"]["raiz"]), self.root.resolve())
        negado = self.cli("operador-juridico", "backup", "verificar", "--origem", str(snap))
        self.assertEqual(negado.returncode, 2, negado.stdout + negado.stderr)

    def test_negativa_fora_da_raiz_lembra_o_raiz(self):
        """Rodando fora da raiz (sem `--raiz`), a negativa pedia só o `--sha256-manifesto`, como num desastre."""
        snap, _ = self.criar_copia()
        registro = self.registro_guardado_sem_livro()
        fora = self.pasta("fora-da-raiz")
        fora.mkdir()
        for acao, extra in (("verificar", []),
                            ("restaurar", ["--destino", str(self.pasta("dest")), "--retiradas", str(registro)])):
            with self.subTest(acao=acao):
                p = self.cli_em("operador-lab", None, fora, "backup", acao, "--origem", str(snap), *extra)
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                erro = json.loads(p.stderr)["error"]
                self.assertEqual(erro["code"], "E_ACCESS_DENIED")
                self.assertIn("--raiz", erro["message"])
                self.assertIn(str(fora.resolve()), erro["message"])
                self.assertIn("--sha256-manifesto", erro["message"])


class TestKit03VerificarNaoLeAtravesDeLigacao(_Revisao):
    def test_kit03_juncao_em_files_nao_e_lida_na_verificacao(self):
        snap = self.pasta("snap")
        backup.create_backup(self.root, snap, "r177-verificar")
        manifesto = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
        alvo = next(f["path"] for f in manifesto["files"] if f["path"].startswith("templates/"))
        fora = self.pasta("fora-templates")
        shutil.copytree(snap / "files" / "templates", fora)
        (fora / Path(alvo).relative_to("templates")).write_text("conteúdo de fora da cópia (fictício)\n",
                                                                encoding="utf-8")
        trocar_pasta_por_ligacao(snap / "files" / "templates", fora)
        abertos, abrir_os, abrir_io = [], os.open, io.open

        def espiar_os(caminho, *args, **kwargs):
            abertos.append(os.path.realpath(caminho))
            return abrir_os(caminho, *args, **kwargs)

        def espiar_io(caminho, *args, **kwargs):
            if isinstance(caminho, (str, os.PathLike)):
                abertos.append(os.path.realpath(caminho))
            return abrir_io(caminho, *args, **kwargs)

        with mock.patch("os.open", side_effect=espiar_os), mock.patch("io.open", side_effect=espiar_io):
            ver = backup.verify_backup(snap)
        de_fora = [p for p in abertos if Path(p).is_relative_to(fora.resolve())]
        self.assertEqual(de_fora, [], "a verificação abriu, através da junção, arquivos de fora da cópia")
        self.assertNotIn(alvo, ver["changed"], "a verificação comparou o conteúdo de fora da cópia")
        self.assertFalse(ver["ok"])
        self.assertIn("templates", ver.get("ligacoes", []))
        self.assertIn(alvo, ver["missing"])
        self.assertIn(os.path.realpath(snap / "files" / "fundacao" / "__init__.py"), abertos,
                      "o espião não viu nem a leitura dos arquivos comuns listados")  # o teste não é vazio


class TestKit04AnexosDeStateNaoSeguemLigacao(_Revisao):
    def setUp(self):
        super().setUp()
        self.tipos = tipos_de_ligacao(self.root)  # vínculo físico sempre; link simbólico onde o sistema deixa
        self.fora = self.pasta("fora")
        self.fora.mkdir()

    def vitima(self, nome: str, conteudo: bytes = b'{"vitima": "arquivo de fora de state/ (ficticio)"}\n') -> Path:
        v = self.fora / nome
        v.write_bytes(conteudo)
        return v

    def test_kit04_backup_nao_anota_a_ancora_no_arquivo_de_fora(self):
        livro = self.root / "state" / backup.LIVRO_COPIAS
        for tipo in self.tipos:
            with self.subTest(tipo=tipo):
                vitima = self.vitima(f"livro-{tipo}.jsonl")
                antes = vitima.read_bytes()
                ligar(livro, vitima, tipo)
                snap = self.pasta(f"snap-{tipo}")
                res = backup.create_backup(self.root, snap, "r177-livro-ligado")
                self.assertEqual(vitima.read_bytes(), antes, "o backup acrescentou a âncora no arquivo de fora")
                self.assertIn("livro de cópias", res.get("aviso", ""))
                self.assertEqual(res["sha256_manifesto"], sha256_de(snap / "manifest.json"))  # a âncora sai mesmo assim
                livro.unlink()
        backup.create_backup(self.root, self.pasta("snap-normal"), "r177-livro-normal")  # sem ligação: anota
        self.assertEqual(len(livro.read_text(encoding="utf-8").splitlines()), 1)

    def test_kit04_registro_protegido_nao_segue_ligacao(self):
        original = self.log.read_bytes()
        linha = {"entity_type": "acl_revoke", "entity_id": "acl:ex-ficticio:read:common", "principal": "ex-ficticio",
                 "resource": "common", "action": "read", "decided_by": "operador-lab",
                 "decided_at": "2026-10-21T00:00:00Z"}
        for tipo in self.tipos:
            with self.subTest(tipo=tipo):
                vitima = self.vitima(f"retiradas-{tipo}.jsonl", original)  # parece o registro, mas é de fora
                self.log.unlink()
                ligar(self.log, vitima, tipo)
                with self.assertRaises(FundacaoError):
                    backup.append_tombstone_log(self.log, linha)
                vazio = self.vitima(f"vazio-{tipo}.jsonl", b"")
                novo = self.root / "state" / f"outro-registro-{tipo}.jsonl"
                ligar(novo, vazio, tipo)
                with self.assertRaises(FundacaoError):
                    backup.ensure_tombstone_log(novo)  # a identidade nova iria para o arquivo de fora
                self.assertEqual((vitima.read_bytes(), vazio.read_bytes()), (original, b""))
                self.log.unlink()
                self.log.write_bytes(original)

    def test_kit04_revogacao_fica_na_fila_e_nao_vai_para_o_arquivo_de_fora(self):
        original = self.log.read_bytes()
        vitima = self.vitima("retiradas-vinculo.jsonl", original)
        self.log.unlink()
        ligar(self.log, vitima, "vinculo-fisico")
        with self.assertRaises(FundacaoError):
            self.policy.revoke(self.admin, "operador-juridico", resource_project("juridico-lab"), "read")
        self.assertEqual(vitima.read_bytes(), original, "a revogação foi gravada no arquivo de fora")
        self.assertEqual(backup.outbox_pending(self.con), 1)  # a intenção continua no banco
        with self.assertRaises(FundacaoError):  # e o backup não nasce com a lacuna
            backup.create_backup(self.root, self.pasta("snap"), "r177-registro-ligado")
        self.log.unlink()
        self.log.write_bytes(original)
        self.assertEqual(backup.flush_outbox(self.con, self.log)["exportadas"], 1)
        self.assertIn('"acl_revoke"', self.log.read_text(encoding="utf-8"))

    def test_kit04_exportacao_de_eventos_nao_segue_ligacao(self):
        pendentes = "SELECT COUNT(*) FROM event WHERE exported = 0"
        for tipo in self.tipos:
            with self.subTest(tipo=tipo):
                vitima = self.vitima(f"eventos-{tipo}.jsonl")
                antes, quantos = vitima.read_bytes(), self.con.execute(pendentes).fetchone()[0]
                destino = self.root / "evidence" / f"eventos-{tipo}.jsonl"
                ligar(destino, vitima, tipo)
                with self.assertRaises(FundacaoError):
                    events.export_jsonl(self.con, destino)
                self.assertEqual(vitima.read_bytes(), antes, "a exportação gravou no arquivo de fora")
                self.assertEqual(self.con.execute(pendentes).fetchone()[0], quantos, "marcou como exportado")
        normal = self.root / "evidence" / "eventos-normal.jsonl"
        self.assertGreater(events.export_jsonl(self.con, normal), 0)
        self.assertEqual(events.export_jsonl(self.con, normal), 0)  # idempotente
        self.assertEqual(len(normal.read_text(encoding="utf-8").splitlines()),
                         self.con.execute("SELECT COUNT(*) FROM event").fetchone()[0])


class TestKit05DestinoCriadoAntes(_Revisao):
    def test_kit05_destino_vazio_criado_antes_e_trocado_com_aviso(self):
        snap = self.pasta("snap")
        snap.mkdir()  # o titular criou a pasta da cópia antes (com as permissões dela)
        res = backup.create_backup(self.root, snap, "r177-destino")
        self.assertIn("pasta de cima", res.get("aviso", ""), "o backup trocou o destino criado antes sem avisar")
        dest = self.pasta("dest")
        dest.mkdir()
        rep = backup.restore(snap, dest, self.log, sha256_manifesto=res["sha256_manifesto"])
        self.assertTrue(rep["released"], rep)
        self.assertIn("pasta de cima", rep.get("aviso_permissoes", ""))
        novo = backup.restore(snap, self.pasta("dest-novo"), self.log, sha256_manifesto=res["sha256_manifesto"])
        self.assertTrue(novo["released"], novo)
        self.assertNotIn("aviso_permissoes", novo)  # destino que não existia: nada a avisar
        outro = backup.create_backup(self.root, self.pasta("snap-novo"), "r177-destino-novo")
        self.assertNotIn("pasta de cima", outro.get("aviso", ""))


if __name__ == "__main__":
    unittest.main()
