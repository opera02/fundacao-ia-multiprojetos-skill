"""Canário do WSL (1.7.10, pacote CANARIO; reconferência REV3, item 3): a configuração do Claude Code do ensaio
(CLAUDE_CONFIG_DIR, onde fica o login do titular) vai para o ext4 da casa, ao lado da do lançador
(`~/.local/share/fundacao-ia/ensaio/config-<id da base>`), criada com `os.mkdir` 0700, com inode e marca no plano, e
recusada se o disco não guardar 0700 (no DrvFs sem `metadata` o modo fica 0777: o login ficaria legível); o `limpar` a
apaga como os temps, sem seguir ligação e sem ler o alvo do plano. A casa é a do teste (`CASA` e o HOME da linha de
comando), nunca a real. Nada abre o Claude Code."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import sys
import unittest
from unittest import mock

from test_ensaio_isolamento import LINUX, Base, copia_do_script, rodar_copia

POSIX = os.name == "posix"


class TestConfigNaCasa(Base):
    def test_preparar_cria_a_config_na_casa_com_0700_e_registra_no_plano(self):
        plano = self.mod.preparar(self.base)
        cfg = self.mod.config_do_ensaio(self.base)
        self.assertEqual(plano["config"]["caminho"], cfg.as_posix())
        self.assertEqual(cfg.parent, self.casa / ".local" / "share" / "fundacao-ia" / "ensaio")
        self.assertRegex(cfg.name, r"^config-[0-9a-f]{16}$")
        st = os.lstat(cfg)
        self.assertEqual((plano["config"]["dev"], plano["config"]["ino"]), (st.st_dev, st.st_ino))
        self.assertRegex(plano["config"]["marca"], r"^[0-9a-f]{16}$")
        marca = (cfg / ".ensaio-isolamento").read_text(encoding="utf-8").strip()
        self.assertEqual(marca, plano["config"]["marca"])
        self.assertFalse((self.base / "config").exists())  # nada de configuração na base (na forma drvfs, /mnt/<x>)
        if POSIX:
            self.assertEqual(self.mod._modo(cfg), 0o700)
            for pasta in (self.casa / ".local", self.casa / ".local" / "share", cfg.parent.parent, cfg.parent):
                self.assertEqual(self.mod._modo(pasta), 0o700, pasta)

    def test_o_nome_sai_da_base_nao_do_plano(self):
        outra = self.tmp / "outra-base"
        self.assertNotEqual(self.mod.config_do_ensaio(self.base), self.mod.config_do_ensaio(outra))
        self.assertEqual(self.mod.config_do_ensaio(self.base), self.mod.config_do_ensaio(self.tmp / "." / "base"))

    def test_preparar_recusa_disco_que_nao_guarda_0700_sem_criar_nada(self):
        """Reproduz a REV3: no DrvFs sem `metadata` o modo fica 0777 depois do chmod 0700."""
        cfg = self.mod.config_do_ensaio(self.base)
        with mock.patch.object(self.mod, "_modo", lambda p: 0o777):
            with self.assertRaises(self.mod.Erro) as ctx:
                self.mod.preparar(self.base)
        self.assertIn("não guarda 0700", str(ctx.exception))
        self.assertFalse(cfg.exists())
        self.assertFalse(self.base.exists())
        self.assertEqual(list(self.temp_base.iterdir()), [])

    def test_preparar_que_falha_depois_da_config_nao_deixa_config_nem_temps(self):
        # REV4: o _criar_config roda antes da base, e nada o desfazia; uma falha depois (disco cheio, pai sem escrita)
        # deixava a configuração órfã, e o preparar seguinte e o limpar recusavam até apagar à mão.
        cfg = self.mod.config_do_ensaio(self.base)
        with mock.patch.object(self.mod, "_gravar_json", side_effect=OSError("disco cheio (simulado)")):
            with self.assertRaises(OSError):
                self.mod.preparar(self.base)
        self.assertFalse(os.path.lexists(cfg))
        self.assertEqual(list(self.temp_base.iterdir()), [])
        plano = self.mod.preparar(self.tmp / "outra-base")  # a casa e o temp continuam usáveis
        self.assertTrue(os.path.isdir(plano["config"]["caminho"]))

    def test_desfazer_nao_apaga_pasta_trocada_nem_arquivo_alheio(self):
        reg = self.mod._criar_config(self.base)
        cfg = self.mod.config_do_ensaio(self.base)
        (cfg / "de-outro.txt").write_text("fica", encoding="utf-8")
        self.mod._desfazer(reg)  # a pasta tem arquivo que o preparar não gravou: fica inteira, com a marca
        self.assertTrue((cfg / "de-outro.txt").exists())
        self.assertTrue((cfg / ".ensaio-isolamento").exists())
        (cfg / "de-outro.txt").unlink()
        self.mod._desfazer({**reg, "ino": reg["ino"] + 1})  # inode de outra pasta: nada é tocado
        self.assertTrue((cfg / ".ensaio-isolamento").exists())
        self.mod._desfazer(reg)  # a pasta que ele criou, só com a marca: sai
        self.assertFalse(os.path.lexists(cfg))

    def test_preparar_recusa_config_que_ja_existe(self):
        cfg = self.mod.config_do_ensaio(self.base)
        cfg.mkdir(parents=True)
        (cfg / "de-outro.txt").write_text("fica", encoding="utf-8")
        with self.assertRaises(self.mod.Erro) as ctx:
            self.mod.preparar(self.base)
        self.assertIn("já existe", str(ctx.exception))
        self.assertTrue((cfg / "de-outro.txt").is_file())
        self.assertFalse(self.base.exists())

    @unittest.skipUnless(LINUX, "ligação simbólica conferida no Linux (o preparo real roda no Ubuntu)")
    def test_preparar_recusa_ligacao_no_caminho_da_casa(self):
        externo = self.tmp / "fora-da-casa"
        externo.mkdir()
        (self.casa / ".local").symlink_to(externo, target_is_directory=True)
        with self.assertRaises(self.mod.Erro) as ctx:
            self.mod.preparar(self.base)
        self.assertIn("ligação", str(ctx.exception))
        self.assertEqual(list(externo.iterdir()), [])
        self.assertFalse(self.base.exists())

    def test_desvios_dizem_onde_fica_a_config(self):
        self.assertTrue(any("~/.local/share/fundacao-ia/ensaio/config-" in d for d in self.mod.DESVIOS_FIXOS))
        self.assertFalse(any("<base>/config" in d for d in self.mod.DESVIOS_FIXOS))

    def test_preparar_pela_cli_mostra_a_config_e_as_sessoes(self):
        script = copia_do_script(self.tmp / "skill")
        r = rodar_copia(script, "preparar", "--base", self.base, "--temp-base", self.temp_base.as_posix(),
                        env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        saida = json.loads(r.stdout)
        cfg = self.mod.config_do_ensaio(self.base)
        self.assertEqual(saida["config"], cfg.as_posix())
        # O comando que o titular cola vai entre aspas quando o caminho tem caractere de shell (o ~ do nome curto 8.3
        # do runner do Windows): o teste compara com a mesma citação, que não muda um caminho comum.
        self.assertIn("CLAUDE_CONFIG_DIR=" + shlex.quote(cfg.as_posix()), saida["proximo_passo"])
        # Revisão de segurança da 1.7.10: +2 sessões (a área root de outro projeto e <raiz>/.claude).
        self.assertEqual(saida["sessoes"], {"com_barramento": 25, "sem_barramento": 24})
        self.assertTrue(cfg.is_dir())

    @unittest.skipUnless(hasattr(os, "geteuid"), "a recusa de root é do POSIX")
    def test_preparar_como_root_recusa_sem_criar_nada(self):
        import contextlib
        import io
        saida = io.StringIO()
        with mock.patch.object(self.mod.os, "geteuid", lambda: 0), contextlib.redirect_stdout(saida):
            codigo = self.mod.main(["preparar", "--base", str(self.base), "--temp-base", self.temp_base.as_posix()])
        self.assertEqual(codigo, 2)
        self.assertIn("sem sudo", json.loads(saida.getvalue())["erro"])
        self.assertFalse(self.base.exists())
        self.assertEqual(list(self.casa.iterdir()), [])


class TestConferirLogin(Base):
    def setUp(self):
        super().setUp()
        self.plano = self.mod.preparar(self.base)
        self.cfg = self.mod.config_do_ensaio(self.base)

    def test_sem_login_recusa_com_o_comando_pronto(self):
        with self.assertRaises(self.mod.Erro) as ctx:
            self.mod.conferir_login(self.base, "/fixo/claude", self.plano)
        self.assertIn("CLAUDE_CONFIG_DIR=" + shlex.quote(self.cfg.as_posix()), str(ctx.exception))
        self.assertIn("/login", str(ctx.exception))

    def test_com_login_devolve_a_config_conferida(self):
        (self.cfg / ".credentials.json").write_text("{}", encoding="utf-8")
        self.assertEqual(self.mod.conferir_login(self.base, "/fixo/claude", self.plano), self.cfg)

    def test_disco_que_nao_guarda_0700_recusa(self):
        (self.cfg / ".credentials.json").write_text("{}", encoding="utf-8")
        with mock.patch.object(self.mod, "_modo", lambda p: 0o777):
            with self.assertRaises(self.mod.Erro) as ctx:
                self.mod.conferir_login(self.base, "/fixo/claude", self.plano)
        self.assertIn("não guarda 0700", str(ctx.exception))

    def test_config_trocada_ou_com_outra_marca_recusa(self):
        (self.cfg / ".credentials.json").write_text("{}", encoding="utf-8")
        (self.cfg / ".ensaio-isolamento").write_text("outra-marca\n", encoding="utf-8")
        with self.assertRaises(self.mod.Erro) as ctx:
            self.mod.conferir_login(self.base, "/fixo/claude", self.plano)
        self.assertIn("não é a configuração criada pelo preparar", str(ctx.exception))

    def test_plano_de_outra_casa_recusa(self):
        outra = self.tmp / "outra-casa"
        outra.mkdir()
        self.mod.CASA = str(outra)
        with self.assertRaises(self.mod.Erro) as ctx:
            self.mod.conferir_login(self.base, "/fixo/claude", self.plano)
        self.assertIn("mesmo usuário do preparar", str(ctx.exception))

    def test_rodar_pela_cli_usa_a_config_da_casa(self):
        """A linha de comando lê a casa do HOME (como o lançador): sem login nela, recusa com o caminho da casa."""
        script = copia_do_script(self.tmp / "skill")
        r = rodar_copia(script, "rodar", "--base", self.base, "--claude", sys.executable,
                        "--temp-base", self.temp_base.as_posix(), env=self.env)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("CLAUDE_CONFIG_DIR=" + shlex.quote(self.cfg.as_posix()), json.loads(r.stdout)["erro"])


class TestLimparConfig(Base):
    def setUp(self):
        super().setUp()
        self.plano = self.mod.preparar(self.base)
        self.cfg = self.mod.config_do_ensaio(self.base)

    def test_limpar_apaga_a_config_com_o_login_e_a_pasta_ensaio_vazia(self):
        (self.cfg / ".credentials.json").write_text("{}", encoding="utf-8")
        (self.cfg / "projects" / "x").mkdir(parents=True)
        (self.cfg / "projects" / "x" / "sessao.jsonl").write_text("{}", encoding="utf-8")
        resumo = self.mod.limpar(self.base)
        self.assertEqual((resumo["sobras"], resumo["restantes"]), ([], []), resumo)
        self.assertFalse(self.cfg.exists())
        self.assertFalse(self.cfg.parent.exists())
        self.assertTrue(self.cfg.parent.parent.is_dir())  # ~/.local/share/fundacao-ia é a área do lançador: fica
        self.assertFalse(self.base.exists())

    def test_limpar_mantem_a_pasta_ensaio_com_a_config_de_outro_ensaio(self):
        vizinha = self.cfg.parent / "config-0123456789abcdef"
        vizinha.mkdir()
        self.mod.limpar(self.base)
        self.assertFalse(self.cfg.exists())
        self.assertTrue(vizinha.is_dir())

    def test_limpar_nao_apaga_config_recriada(self):
        """O inode do plano tem de bater (a pasta recriada com o mesmo nome não é a do preparar)."""
        shutil.rmtree(self.cfg)
        self.cfg.mkdir()
        (self.cfg / "de-outro.txt").write_text("fica", encoding="utf-8")
        resumo = self.mod.limpar(self.base)
        self.assertTrue((self.cfg / "de-outro.txt").is_file())
        self.assertTrue(any("não é a configuração criada pelo preparar" in s for s in resumo["sobras"]), resumo)
        self.assertTrue((self.base / "plano.json").is_file())

    def test_limpar_nao_apaga_config_com_a_marca_trocada(self):
        (self.cfg / ".ensaio-isolamento").write_text("outra-marca\n", encoding="utf-8")
        (self.cfg / ".credentials.json").write_text("{}", encoding="utf-8")
        resumo = self.mod.limpar(self.base)
        self.assertTrue((self.cfg / ".credentials.json").is_file())
        self.assertTrue(any("marca" in s for s in resumo["sobras"]), resumo)
        self.assertTrue((self.base / "plano.json").is_file())

    def test_limpar_de_outra_casa_avisa_e_mantem_o_plano(self):
        outra = self.tmp / "outra-casa"
        outra.mkdir()
        self.mod.CASA = str(outra)
        resumo = self.mod.limpar(self.base)
        self.assertTrue(any("outra casa" in s for s in resumo["sobras"]), resumo)
        self.assertTrue(self.cfg.is_dir())
        self.assertTrue((self.base / "plano.json").is_file())

    def test_limpar_ignora_o_alvo_adulterado_no_plano(self):
        """O plano só restringe: um caminho trocado nele não aponta o que o limpar apaga."""
        alvo = self.tmp / "dados-do-titular"
        alvo.mkdir()
        (alvo / "importante.txt").write_text("não apague", encoding="utf-8")
        plano = json.loads((self.base / "plano.json").read_text(encoding="utf-8"))
        st = os.lstat(alvo)
        plano["config"] = {"caminho": alvo.as_posix(), "dev": st.st_dev, "ino": st.st_ino,
                           "marca": plano["config"]["marca"]}
        (self.base / "plano.json").write_text(json.dumps(plano), encoding="utf-8", newline="\n")
        resumo = self.mod.limpar(self.base)
        self.assertTrue((alvo / "importante.txt").is_file())
        self.assertTrue(self.cfg.is_dir())  # a da base também fica (o plano não confere)
        self.assertTrue(resumo["sobras"], resumo)

    @unittest.skipUnless(LINUX, "ligação simbólica conferida no Linux (o limpar real roda no Ubuntu)")
    def test_limpar_nao_apaga_config_que_virou_ligacao(self):
        externo = self.tmp / "dados-reais"
        externo.mkdir()
        (externo / "importante.txt").write_text("não apague", encoding="utf-8")
        shutil.rmtree(self.cfg)
        self.cfg.symlink_to(externo, target_is_directory=True)
        resumo = self.mod.limpar(self.base)
        self.assertTrue((externo / "importante.txt").is_file())
        self.assertTrue(any("ligação" in s for s in resumo["sobras"]), resumo)

    @unittest.skipUnless(LINUX, "ligação simbólica conferida no Linux (o limpar real roda no Ubuntu)")
    def test_limpar_nao_segue_ligacao_no_caminho_da_casa(self):
        """`ensaio/` trocada por ligação para a mesma pasta (mesmo inode): o caminho da casa não passa por ligação."""
        real = self.tmp / "ensaio-movida"
        self.cfg.parent.rename(real)
        self.cfg.parent.symlink_to(real, target_is_directory=True)
        resumo = self.mod.limpar(self.base)
        self.assertTrue((real / self.cfg.name).is_dir())
        self.assertTrue(any("ligação" in s for s in resumo["sobras"]), resumo)


if __name__ == "__main__":
    unittest.main()
