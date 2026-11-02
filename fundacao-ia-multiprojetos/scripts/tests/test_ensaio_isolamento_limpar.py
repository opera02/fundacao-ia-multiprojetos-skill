"""Canário do WSL (1.7.10, pacote CANARIO; reconferência REV2): o `limpar` conhece o que as próprias sondas deixam
(pedidos, respostas, perfil gerado, arquivos fora do projeto, temps do lançador, configuração e cache do Claude Code,
marcadores de 0 byte do sandbox), devolve o que restou e só apaga o plano quando não sobra nada do ensaio; o `rodar`
recusa base já rodada (evidência velha não vale). Pastas descartáveis; nada abre o Claude Code."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest

from apoio import ENV, SCRIPTS
from test_ensaio_isolamento import LINUX, Base, _ctx, executor_bom


class TestLimparArtefatos(Base):
    def _rodada(self):
        """Uma rodada que deixa todos os artefatos possíveis (como uma sessão real, que vaza ou não)."""
        plano = self.mod.preparar(self.base)
        c = self.mod._caminhos(self.base)
        for arq in (c["pedido"], c["pedido_so"], c["perfil"], c["fora1"], c["fora2"], c["resposta"]):
            arq.write_text("x", encoding="utf-8")
        c["respostas_x"].mkdir()
        c["resposta_x"].write_text("x", encoding="utf-8")
        claude_tmp = c["tmp_a"] / "claude-1000" / "sessao"
        claude_tmp.mkdir(parents=True)
        (claude_tmp / "saida.txt").write_text("saída do Claude Code", encoding="utf-8")
        (c["cache_a"] / "pip" / "http").mkdir(parents=True)
        (c["cache_a"] / "pip" / "http" / "x.bin").write_bytes(b"cache")
        config = self.mod.config_do_ensaio(self.base)  # a configuração do ensaio, na casa (REV3)
        (config / "projects" / "x").mkdir(parents=True)
        (config / "projects" / "x" / "sessao.jsonl").write_text("{}", encoding="utf-8")
        (config / ".credentials.json").write_text("{}", encoding="utf-8")
        (c["janelas"] / ".ssh").mkdir()
        (c["janelas"] / ".codex").write_bytes(b"")
        return plano, c

    def test_limpar_apaga_os_artefatos_da_rodada_e_a_base(self):
        _, c = self._rodada()
        resumo = self.mod.limpar(self.base)
        self.assertEqual(resumo["sobras"], [], resumo)
        self.assertEqual(resumo["restantes"], [])
        self.assertFalse(self.base.exists())
        self.assertFalse(c["tmp_a"].exists())
        self.assertFalse(c["tmp_b"].exists())
        self.assertFalse(self.mod.config_do_ensaio(self.base).exists())  # com o login e as transcrições

    def test_limpar_com_restante_mantem_o_plano_e_o_lista(self):
        """Reproduz a REV2: com sobras vazias, o plano saía e a base ficava com o perfil, sem aviso."""
        self.mod.preparar(self.base)
        (self.base / "deixado-por-alguem.txt").write_text("fica", encoding="utf-8")
        resumo = self.mod.limpar(self.base)
        self.assertEqual(resumo["restantes"], ["deixado-por-alguem.txt"])
        self.assertTrue((self.base / "plano.json").is_file())
        self.assertTrue((self.base / "deixado-por-alguem.txt").is_file())

    def test_limpar_apaga_os_marcadores_de_zero_byte_e_mantem_os_com_conteudo(self):
        self.mod.preparar(self.base)
        c = self.mod._caminhos(self.base)
        for pasta in (self.base, c["proj_dir"], c["a"]):
            (pasta / ".bashrc").write_bytes(b"")
            (pasta / ".vscode").mkdir()
        (c["a"] / ".git" / "hooks").mkdir(parents=True)
        (c["a"] / ".git" / "config").write_bytes(b"")
        (self.base / "registry").mkdir()
        (c["a"] / ".gitconfig").write_text("[user]\n", encoding="utf-8")  # com conteúdo: é dado e fica
        resumo = self.mod.limpar(self.base)
        self.assertEqual(resumo["restantes"], ["projects/", "projects/ensaio-a/", "projects/ensaio-a/.gitconfig"])
        self.assertTrue((c["a"] / ".gitconfig").is_file())
        for pasta in (self.base, c["proj_dir"], c["a"]):
            self.assertFalse((pasta / ".bashrc").exists())
            self.assertFalse((pasta / ".vscode").exists())
        self.assertFalse((c["a"] / ".git").exists())
        self.assertTrue((self.base / "plano.json").is_file())

    def test_limpar_nao_apaga_temp_de_outro_inode(self):
        self.mod.preparar(self.base)
        c = self.mod._caminhos(self.base)
        shutil.rmtree(c["tmp_a"])
        c["tmp_a"].mkdir()  # outra pasta com o mesmo nome (de outro ensaio?): inode diferente do plano
        (c["tmp_a"] / "de-outro.txt").write_text("não apague", encoding="utf-8")
        resumo = self.mod.limpar(self.base)
        self.assertTrue((c["tmp_a"] / "de-outro.txt").is_file())
        self.assertTrue(any("inode diferente" in s for s in resumo["sobras"]), resumo)
        self.assertTrue((self.base / "plano.json").is_file())

    def test_limpar_nao_apaga_temp_com_a_marca_trocada(self):
        """O inode sozinho não basta (o ext4 reaproveita o número): a marca aleatória do plano também tem de bater."""
        self.mod.preparar(self.base)
        c = self.mod._caminhos(self.base)
        (c["tmp_a"] / ".ensaio-isolamento").write_text("outra-marca\n", encoding="utf-8")
        (c["tmp_a"] / "dado.txt").write_text("fica", encoding="utf-8")
        resumo = self.mod.limpar(self.base)
        self.assertTrue((c["tmp_a"] / "dado.txt").is_file())
        self.assertTrue(any("marca" in s for s in resumo["sobras"]), resumo)
        self.assertFalse(c["tmp_b"].exists())  # o outro temp, com a marca certa, sai

    def test_limpar_com_outro_temp_base_avisa_e_mantem_o_plano(self):
        """Com o --temp-base errado, os temps do ensaio ficariam órfãos: o limpar avisa e guarda o plano."""
        self.mod.preparar(self.base)
        outro = self.tmp / "outro-temp"
        outro.mkdir()
        resumo = self.mod.limpar(self.base, temp_base=outro.as_posix())
        self.assertTrue(any("--temp-base" in s for s in resumo["sobras"]), resumo)
        self.assertTrue((self.base / "plano.json").is_file())
        self.assertTrue((self.temp_base / "fundacao-ia-ensaio-a").is_dir())

    @unittest.skipUnless(LINUX, "ligação simbólica conferida no Linux (o limpar real roda no Ubuntu)")
    def test_limpar_nao_segue_ligacao_dentro_do_temp_nem_do_cache(self):
        self.mod.preparar(self.base)
        c = self.mod._caminhos(self.base)
        externo = self.tmp / "dados-reais"
        externo.mkdir()
        (externo / "importante.txt").write_text("não apague", encoding="utf-8")
        (c["tmp_a"] / "atalho").symlink_to(externo, target_is_directory=True)
        (c["cache_a"] / "atalho").symlink_to(externo, target_is_directory=True)
        (self.mod.config_do_ensaio(self.base) / "arquivo").symlink_to(externo / "importante.txt")
        resumo = self.mod.limpar(self.base)
        self.assertTrue((externo / "importante.txt").is_file())
        self.assertEqual(resumo["sobras"], [], resumo)
        self.assertFalse(self.base.exists())

    @unittest.skipUnless(LINUX, "ligação simbólica conferida no Linux (o limpar real roda no Ubuntu)")
    def test_limpar_nao_apaga_temp_que_virou_ligacao(self):
        self.mod.preparar(self.base)
        c = self.mod._caminhos(self.base)
        externo = self.tmp / "dados-reais"
        externo.mkdir()
        (externo / "importante.txt").write_text("não apague", encoding="utf-8")
        shutil.rmtree(c["tmp_b"])
        c["tmp_b"].symlink_to(externo, target_is_directory=True)
        resumo = self.mod.limpar(self.base)
        self.assertTrue((externo / "importante.txt").is_file())
        self.assertTrue(any("ligação" in s for s in resumo["sobras"]), resumo)


class TestRodarDeNovo(Base):
    def test_rodar_duas_vezes_na_mesma_base_recusa(self):
        plano = self.mod.preparar(self.base)
        kw = {"perfil_info": {"gerado": True}, "sandbox_ligado": True, "linux": True, "contexto": _ctx()}
        self.mod.rodar(self.base, executor=executor_bom(plano["nonce"]), **kw)
        self.assertIn("rodado_em", json.loads((self.base / "plano.json").read_text(encoding="utf-8")))
        with self.assertRaises(self.mod.Erro) as ctx:
            self.mod.rodar(self.base, executor=executor_bom(plano["nonce"]), **kw)
        self.assertIn("limpar", str(ctx.exception))

    def test_artefato_velho_recusa_antes_de_qualquer_sessao(self):
        """Reproduz a REV2: um pedido de rodada anterior dava `passou` na fila com a gravação nova falhando."""
        plano = self.mod.preparar(self.base)
        c = self.mod._caminhos(self.base)
        chamadas = []

        def exe(base, proj, sessao):
            chamadas.append(sessao["rotulo"])
            return executor_bom(plano["nonce"])(base, proj, sessao)

        for arq in (c["pedido_so"], c["fora1"]):
            arq.write_text("velho", encoding="utf-8")
            with self.subTest(arquivo=arq.name):
                with self.assertRaises(self.mod.Erro):
                    self.mod.rodar(self.base, executor=exe, perfil_info={"gerado": True}, sandbox_ligado=True,
                                   linux=True, contexto=_ctx())
            arq.unlink()
        self.assertEqual(chamadas, [])

    def test_main_recusa_base_com_perfil_de_rodada_anterior(self):
        """Pela linha de comando, com um binário qualquer que responde `--version` (o próprio Python, x.y.z)."""
        self.mod.preparar(self.base)
        self.mod._caminhos(self.base)["perfil"].write_text("{}", encoding="utf-8")
        r = subprocess.run([sys.executable, "-B", str(SCRIPTS / "ensaio_isolamento_wsl.py"), "rodar", "--base",
                            str(self.base), "--claude", sys.executable, "--temp-base", self.temp_base.as_posix()],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV, timeout=120)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("perfil-ensaio-a.settings.json", json.loads(r.stdout)["erro"])
        self.assertNotIn("rodado_em", json.loads((self.base / "plano.json").read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
