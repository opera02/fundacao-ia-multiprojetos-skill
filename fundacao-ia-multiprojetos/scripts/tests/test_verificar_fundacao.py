"""Rotina de operação: só metadados necessários, sem executar a raiz nem alterar seu banco."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import SCRIPTS, SKILL, criar_ligacao_dir, rodar_script
from test_retomada import OBRIGATORIOS, preencher

CANARIO = "CONTEUDO-FICTICIO-NAO-DEVE-SAIR"


def carregar():
    spec = importlib.util.spec_from_file_location("_verificar_rotina", SCRIPTS / "verificar_fundacao.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestVerificarFundacao(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="verificar-fundacao-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.raiz, self.perfil = self.base / "fundacao-ficticia", self.base / "perfil-ficticio"
        (self.raiz / "registry").mkdir(parents=True)
        self.perfil.mkdir()
        (self.raiz / "RETOMADA.md").write_text(preencher(OBRIGATORIOS), encoding="utf-8")
        shutil.copyfile(SKILL / "assets/templates/MATRIZ-REQUISITOS.csv", self.raiz / "registry/requisitos.csv")
        for script, args in (("instrucoes_raiz.py", ["gerar", "--raiz", self.raiz]),
                             ("inventariar_host.py", ["gravar", "--raiz", self.raiz, "--perfil", self.perfil,
                                                      "--saida", self.raiz / "registry/inventario-host.json"])):
            p = rodar_script(script, *args)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def rodar(self, *args):
        p = rodar_script("verificar_fundacao.py", "--raiz", self.raiz, "--perfil", self.perfil, *args, timeout=40)
        self.assertIn(p.returncode, (0, 1), p.stdout + p.stderr)
        try:
            return p.returncode, json.loads(p.stdout)
        except ValueError:
            self.fail("verificador não produziu JSON: " + p.stdout[-300:] + p.stderr[-300:])

    def estado(self):
        return {p.relative_to(self.raiz).as_posix(): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
                for p in self.raiz.rglob("*") if p.is_file()}

    def test_rapido_confere_quatro_passos_sem_criar_banco_ou_declarar_pronto(self):
        antes = self.estado()
        code, res = self.rodar()
        self.assertEqual(code, 1, res)
        self.assertIs(res["pronto_para_seguir"], False)
        passos = {p["id"]: p for p in res["passos"]}
        self.assertEqual(set(passos), {"kit", "retomada", "matriz", "instrucoes", "host", "cadeia", "backup"})
        for nome in ("retomada", "matriz", "instrucoes", "host"):
            self.assertEqual(passos[nome]["estado"], "ok", passos[nome])
        for nome in ("kit", "cadeia", "backup"):
            self.assertEqual(passos[nome]["estado"], "nao_rodado", passos[nome])
            self.assertTrue(passos[nome]["acao"])
        self.assertEqual(self.estado(), antes)
        self.assertFalse((self.raiz / "state").exists())

    def test_inventario_sem_statusline_nao_declara_host_conferido(self):
        arquivo = self.raiz / "registry/inventario-host.json"
        antes = json.loads(arquivo.read_text(encoding="utf-8"))
        antes.pop("status_lines", None)
        arquivo.write_text(json.dumps(antes), encoding="utf-8")
        _, res = self.rodar()
        host = next(p for p in res["passos"] if p["id"] == "host")
        self.assertEqual(host["estado"], "nao_rodado", host)
        self.assertIs(res["pronto_para_seguir"], False)

    def _conferir_com_leitor_real(self, nome, alvo, *, completo=False):
        mod = carregar()
        spec = importlib.util.spec_from_file_location("_leitor_revisao", SCRIPTS / nome)
        leitor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(leitor)
        executar_original, abrir_original = mod.executar, Path.open
        abertos = []

        def abrir(caminho, *args, **kwargs):
            if Path(caminho) == alvo:
                abertos.append(str(caminho))
            return abrir_original(caminho, *args, **kwargs)

        def executar(cmd, timeout):
            if any(Path(str(a)).name == nome for a in cmd):
                if nome == "atualizar_fundacao.py":
                    return 0, leitor.checar(self.raiz), ""
                leitor.inventario(self.perfil, self.raiz)
                return 0, {"ok": True}, ""
            return executar_original(cmd, timeout)

        with mock.patch.object(Path, "open", abrir), mock.patch.object(mod, "executar", executar):
            res = mod.verificar(self.raiz, completo=completo, perfil=self.perfil)
        self.assertEqual(abertos, [], "o dado foi aberto antes da recusa")
        return {p["id"]: p for p in res["passos"]}

    def test_kit_recusa_hardlink_transitivo_antes_da_leitura(self):
        (self.raiz / "state").mkdir()
        con = sqlite3.connect(self.raiz / "state/state.sqlite")
        con.execute("CREATE TABLE ficticia (id)")
        con.commit()
        con.close()
        (self.raiz / "fundacao").mkdir()
        (self.raiz / "fundacao/__init__.py").write_text('KIT_VERSION = "1.7.9"\n', encoding="utf-8")
        dado = self.raiz / "projects/outro/data/documento.txt"
        dado.parent.mkdir(parents=True)
        dado.write_text(CANARIO, encoding="utf-8")
        alias = self.raiz / "fundacao/alias.txt"
        os.link(dado, alias)
        passos = self._conferir_com_leitor_real("atualizar_fundacao.py", alias, completo=True)
        self.assertEqual(passos["kit"]["estado"], "falhou", passos)

    def test_host_recusa_config_hardlinked_antes_da_leitura(self):
        dado = self.raiz / "projects/outro/data/documento.json"
        dado.parent.mkdir(parents=True)
        dado.write_text('{"segredo": "' + CANARIO + '"}', encoding="utf-8")
        alias = self.perfil / ".claude/settings.json"
        alias.parent.mkdir()
        os.link(dado, alias)
        passos = self._conferir_com_leitor_real("inventariar_host.py", alias)
        self.assertEqual(passos["host"]["estado"], "falhou", passos)

    def test_host_recusa_script_em_outro_projeto_antes_de_abrir(self):
        dado = self.raiz / "projects/outro/data/roteiro.py"
        dado.parent.mkdir(parents=True)
        dado.write_text(CANARIO, encoding="utf-8")
        config = self.perfil / ".claude/settings.json"
        config.parent.mkdir()
        config.write_text(json.dumps({"hooks": {"SessionStart": [{"hooks": [
            {"type": "command", "command": "python", "args": [str(dado)]}]}]}}), encoding="utf-8")
        passos = self._conferir_com_leitor_real("inventariar_host.py", dado)
        self.assertEqual(passos["host"]["estado"], "falhou", passos)

    def test_codigo_com_desvio_sigiloso_recusa_antes_de_ler_decisoes(self):
        mod = carregar()
        politica = json.loads((SKILL / "assets/fundacao-kit/registry/route_policy.json").read_text(encoding="utf-8"))
        politica["task_routes"]["sigiloso"] = ["simulado"]
        (self.raiz / "registry/route_policy.json").write_text(json.dumps(politica), encoding="utf-8")
        decisao = self.raiz / "projects/outro/decisoes/aceite.json"
        decisao.parent.mkdir(parents=True)
        decisao.write_text(CANARIO, encoding="utf-8")
        original, abertos = Path.open, []

        def abrir(caminho, *args, **kwargs):
            if Path(caminho) == decisao:
                abertos.append(str(caminho))
            return original(caminho, *args, **kwargs)

        with mock.patch.object(Path, "open", abrir):
            seguro = mod.codigo_seguro(self.raiz)
        self.assertEqual(abertos, [], "uma decisao foi aberta pelo pre-flight")
        self.assertFalse(seguro, "o desvio requer leituras de projeto que a rotina nao autoriza")

    def test_estado_caminho_recusa_travessia_antes_de_abspath(self):
        mod = carregar()
        self.assertEqual(mod.estado_caminho(self.raiz / "registry/../AGENTS.md"), "recusado")

    def test_host_recusa_script_com_ponto_ponto_antes_de_normalizar(self):
        mod = carregar()
        hooks = self.perfil / ".claude/hooks"
        hooks.mkdir(parents=True)
        (hooks / "roteiro.py").write_text("# ficticio", encoding="utf-8")
        arquivo = self.perfil / ".claude/settings.json"
        arquivo.write_text(json.dumps({"hooks": {"SessionStart": [{"hooks": [
            {"type": "command", "command": "python", "args": [str(hooks / "elo/../roteiro.py")]}]}]}}),
            encoding="utf-8")
        self.assertFalse(mod.host_seguro(self.raiz, self.perfil),
                         "normalizar .. antes do leitor real pode esconder um elo POSIX")

    def test_agents_defasado_acusa_sem_reescrever(self):
        arq = self.raiz / "AGENTS.md"
        arq.write_text(arq.read_text(encoding="utf-8").replace("Leia `RETOMADA.md`", "Regra antiga"), encoding="utf-8")
        antes = self.estado()
        _, res = self.rodar()
        p = next(p for p in res["passos"] if p["id"] == "instrucoes")
        self.assertEqual(p["estado"], "falhou", res)
        self.assertIn("instrucoes_raiz.py", p["acao"])
        self.assertEqual(self.estado(), antes)

    def test_ausente_nao_e_sucesso_e_nao_expoe_erro_do_arquivo(self):
        (self.raiz / "RETOMADA.md").unlink()
        (self.raiz / "registry/requisitos.csv").write_text(CANARIO, encoding="utf-8")
        _, res = self.rodar("--completo")
        passos = {p["id"]: p for p in res["passos"]}
        self.assertEqual(passos["retomada"]["estado"], "nao_rodado")
        self.assertEqual(passos["matriz"]["estado"], "falhou")
        self.assertIs(res["pronto_para_seguir"], False)
        self.assertNotIn(CANARIO, json.dumps(res))

    def test_cadeia_false_com_codigo_zero_falha_sem_importar_raiz_ou_alterar_banco(self):
        (self.raiz / "state").mkdir()
        banco = self.raiz / "state/state.sqlite"
        con = sqlite3.connect(banco)
        con.execute("CREATE TABLE event (seq INTEGER, event_id, ts, schema_version, kind, project_id, subject, "
                    "run_id, task_id, payload_json, prev_hash, hash)")
        con.execute("INSERT INTO event VALUES (1,'e','t','v','ficticio',NULL,NULL,NULL,NULL,'{}','errado','errado')")
        con.commit()
        con.close()
        (self.raiz / "fundacao").mkdir()
        marcador = self.base / "codigo-da-raiz-executou"
        codigo = f"from pathlib import Path\nPath({str(marcador)!r}).write_text({CANARIO!r})\n"
        (self.raiz / "fundacao/__init__.py").write_text(codigo, encoding="utf-8")
        (self.raiz / "json.py").write_text(codigo, encoding="utf-8")
        antes = self.estado()
        _, res = self.rodar("--completo")
        p = next(p for p in res["passos"] if p["id"] == "cadeia")
        self.assertEqual(p["estado"], "falhou", res)
        self.assertNotIn(CANARIO, json.dumps(res))
        self.assertFalse(marcador.exists(), "código não conferido da raiz foi executado")
        self.assertEqual(self.estado(), antes)

    def test_backup_sem_hash_externo_fica_nao_rodado(self):
        backup = self.base / "ultima-copia-ficticia"
        backup.mkdir()
        (backup / "manifest.json").write_text(CANARIO, encoding="utf-8")
        _, res = self.rodar("--completo", "--backup", backup)
        p = next(p for p in res["passos"] if p["id"] == "backup")
        self.assertEqual(p["estado"], "nao_rodado")
        self.assertNotIn(CANARIO, json.dumps(res))

    def test_backup_sem_politica_viva_nao_recorrera_a_acl_da_copia(self):
        (self.raiz / "state").mkdir()
        con = sqlite3.connect(self.raiz / "state/state.sqlite")
        con.execute("CREATE TABLE ficticia (id)")
        con.commit()
        con.close()
        backup = self.base / "copia-sem-politica"
        backup.mkdir()
        manifesto = backup / "manifest.json"
        manifesto.write_text(CANARIO, encoding="utf-8")  # não é sequer JSON; não deve chegar ao verify_backup
        antes = self.estado(), manifesto.read_bytes(), manifesto.stat().st_mtime_ns
        _, res = self.rodar("--completo", "--backup", backup, "--sha256-manifesto", "a" * 64)
        p = next(p for p in res["passos"] if p["id"] == "backup")
        self.assertEqual(p["estado"], "falhou", res)
        self.assertNotIn(CANARIO, json.dumps(res))
        self.assertEqual((self.estado(), manifesto.read_bytes(), manifesto.stat().st_mtime_ns), antes)

    def test_saida_nova_em_evidence_e_exclusiva(self):
        saida = self.raiz / "evidence/rotina/resultado.json"
        _, res = self.rodar("--saida", saida)
        self.assertEqual(json.loads(saida.read_text(encoding="utf-8")), res)
        antes = saida.read_bytes()
        _, erro = self.rodar("--saida", saida)
        self.assertIs(erro["pronto_para_seguir"], False)
        self.assertIn("erro", erro)
        self.assertEqual(saida.read_bytes(), antes)
        alvo = self.raiz / "evidence/elo.json"
        os.link(saida, alvo)
        _, erro = self.rodar("--saida", alvo)
        self.assertIn("erro", erro)
        self.assertEqual(saida.read_bytes(), antes)

    def test_saida_fora_de_evidencias_ou_em_ligacao_recusada_sem_escrever(self):
        fora = self.base / "fora"
        fora.mkdir()
        (self.raiz / "evidence").mkdir()
        criar_ligacao_dir(self.raiz / "evidence/atalho", fora)
        for destino in (fora / "resultado.json", self.raiz / "state/resultado.json",
                        self.raiz / "registry/resultado.json", self.raiz / "evidence/atalho/resultado.json",
                        self.raiz / "projects/outro-projeto/outputs/resultado.json"):
            with self.subTest(destino=destino.name):
                _, res = self.rodar("--saida", destino)
                self.assertIn("erro", res)
                self.assertFalse(destino.exists())

    def test_saida_nao_grava_quando_raiz_fica_em_state_ou_dados(self):
        for relativo in ("state", "projects/projeto-ficticio/data"):
            raiz = self.raiz / relativo
            raiz.mkdir(parents=True, exist_ok=True)
            saida = raiz / "evidence/resultado.json"
            _, res = self.rodar("--raiz", raiz, "--saida", saida)
            self.assertIn("erro", res)
            self.assertFalse(saida.exists(), "raiz protegida não pode autorizar escrita de evidência")

    def test_wal_fica_nao_rodado_sem_criar_arquivos_auxiliares(self):
        (self.raiz / "state").mkdir()
        db = self.raiz / "state/state.sqlite"
        con = sqlite3.connect(db)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE ficticia (id)")
        con.commit()
        con.close()
        antes = self.estado()
        _, res = self.rodar("--completo")
        for p in res["passos"]:
            if p["id"] in ("kit", "cadeia", "backup"):
                self.assertEqual(p["estado"], "nao_rodado", res)
        self.assertEqual(self.estado(), antes)

    def test_pronto_so_com_sete_resultados_positivos_e_backup_autorizado(self):
        mod = carregar()
        (self.raiz / "state").mkdir()
        con = sqlite3.connect(self.raiz / "state/state.sqlite")
        con.execute("CREATE TABLE ficticia (id)")
        con.commit()
        con.close()
        (self.raiz / "fundacao").mkdir()
        (self.raiz / "fundacao/__init__.py").write_text('KIT_VERSION = "1.7.8"\n', encoding="utf-8")
        backup = self.base / "copia-ficticia"
        backup.mkdir()

        def executar(cmd, timeout):
            if "checar" in cmd:
                return 0, {"pode_aplicar": True, "nada_a_fazer": True,
                           "cadeia_de_eventos": {"cadeia_integra": True}}, ""
            if "-c" in cmd:
                if "verify_backup" in cmd[cmd.index("-c") + 1]:
                    return 0, {"ok": True, "autorizado": autorizado, "ancora_conferida": True}, ""
                return 0, {"cadeia_integra": True, "primeiro_evento_quebrado": None}, ""
            return 0, {"ok": True}, ""

        for autorizado in (True, False):
            with self.subTest(autorizado=autorizado), mock.patch.object(mod, "executar", executar):
                res = mod.verificar(self.raiz, completo=True, perfil=self.perfil,
                                    backup=backup, sha256_manifesto="a" * 64)
                self.assertIs(res["pronto_para_seguir"], autorizado, res)
                if not autorizado:
                    self.assertEqual(res["passos"][-1]["estado"], "falhou")

    def test_kit_recusa_registro_com_vinculo_fisico_antes_do_verificador(self):
        mod = carregar()
        (self.raiz / "state").mkdir()
        con = sqlite3.connect(self.raiz / "state/state.sqlite")
        con.execute("CREATE TABLE ficticia (id)")
        con.commit()
        con.close()
        (self.raiz / "fundacao").mkdir()
        (self.raiz / "fundacao/__init__.py").write_text('KIT_VERSION = "1.7.8"\n', encoding="utf-8")
        fonte = self.base / "outro-registro.json"
        fonte.write_text("[]", encoding="utf-8")
        os.link(fonte, self.raiz / "registry/kit_install.json")
        resultado = {"pode_aplicar": True, "nada_a_fazer": True, "cadeia_de_eventos": {"cadeia_integra": True}}
        with mock.patch.object(mod, "executar", return_value=(0, resultado, "")):
            res = mod.verificar(self.raiz, completo=True, perfil=self.perfil)
        self.assertEqual(res["passos"][0]["estado"], "falhou", res)

    def test_host_usa_perfil_atual_por_padrao_em_vez_do_perfil_do_inventario(self):
        mod = carregar()

        def executar(cmd, timeout):
            if any(Path(str(a)).name == "inventariar_host.py" for a in cmd):
                return 0, {"ok": "--perfil" in cmd and cmd[cmd.index("--perfil") + 1] == Path.home()}, ""
            return 0, {"ok": True}, ""

        with mock.patch.object(Path, "home", return_value=self.perfil), mock.patch.object(mod, "executar", executar):
            res = mod.verificar(self.raiz)
        host = next(p for p in res["passos"] if p["id"] == "host")
        self.assertEqual(host["estado"], "ok", res)

    def test_timeout_e_json_inesperado_nao_repassam_saida_sensivel(self):
        mod = carregar()
        for efeito in (subprocess.TimeoutExpired(["python"], 1, output=CANARIO, stderr=CANARIO),
                       subprocess.CompletedProcess(["python"], 0, CANARIO, CANARIO),
                       subprocess.CompletedProcess(["python"], 0, '["' + CANARIO + '"]', CANARIO)):
            with self.subTest(tipo=type(efeito).__name__):
                kw = {"side_effect": efeito} if isinstance(efeito, Exception) else {"return_value": efeito}
                with mock.patch.object(mod.subprocess, "run", **kw):
                    codigo, dados, erro = mod.executar(["python", "-I"], 1)
                self.assertNotEqual(erro, "")
                self.assertIsNone(dados)
                self.assertNotIn(CANARIO, str((codigo, dados, erro)))


if __name__ == "__main__":
    unittest.main()
