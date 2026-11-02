"""plugin_candidato.py: ligação, junção, vínculo físico e FIFO no candidato e na origem (1.7.10; contratos do lote 2,
§8; crítica do desenho: "nenhuma cópia segue ligação", com teste de uma ligação para fora). Rodados no Windows e no
Ubuntu (pelo `wsl --cd`, nas pastas temporárias do ext4): onde o sistema não deixa criar a ligação, o teste pula com
o motivo. O conteúdo de fora é um canário fictício que nunca pode aparecer no resultado nem no candidato.
"""

from __future__ import annotations

import json
import os
import unittest

from apoio import criar_ligacao_dir
from test_plugin_candidato import SKILL_OK, MOD, VARIAVEL_PROJETO, VARIAVEL_RAIZ, Fundacao, escrever

CANARIO = "CANARIO-FICTICIO de outro projeto"


class Ligacoes(Fundacao):
    def canario(self):
        fora = self.outro / "segredo-ficticio"
        escrever(fora, {"nota.md": CANARIO + "\n", "SKILL.md": SKILL_OK})
        return fora

    def link_de_arquivo(self, link, alvo):
        try:
            link.symlink_to(alvo)
        except OSError as exc:
            self.skipTest(f"link simbólico de arquivo indisponível neste ambiente: {exc}")

    def vinculo(self, link, alvo):
        try:
            os.link(alvo, link)
        except OSError as exc:
            self.skipTest(f"vínculo físico indisponível neste ambiente: {exc}")

    def fifo(self, caminho):
        try:
            os.mkfifo(caminho)
        except OSError as exc:  # o DrvFs do WSL (/mnt/c) dá Errno 95
            self.skipTest(f"FIFO indisponível neste sistema de arquivos: {exc}")

    def recusa_no_candidato(self, pasta, trecho):
        res = MOD.conferir(pasta)
        self.assertFalse(res["conforme"])
        self.assertTrue(any(trecho in m for m in res["motivos"]), res["motivos"])
        self.assertNotIn("CANARIO", json.dumps(res, ensure_ascii=False))
        with self.assertRaises(MOD.CandidatoRecusado):
            MOD.manifesto(pasta)
        texto, _res = MOD.revisar(pasta)
        self.assertNotIn("CANARIO", texto)

    def nada_montado(self):
        # O montar só grava em plugins-candidatos/: vazia (ou ausente), nada de fora chegou ao projeto por ele.
        candidatos = self.proj / "plugins-candidatos"
        if candidatos.exists():
            self.assertEqual(list(candidatos.iterdir()), [], "nem o candidato nem o temporário da montagem")


class TestLigacoesNoCandidato(Ligacoes, unittest.TestCase):
    def test_pasta_ligada_para_outro_projeto_recusa(self):
        fora = self.canario()
        pasta = self.candidato()
        criar_ligacao_dir(pasta / "skills" / "ola" / "atalho", fora)
        self.recusa_no_candidato(pasta, "ligação")

    def test_skill_inteira_ligada_recusa(self):
        fora = self.canario()
        pasta = self.candidato()
        criar_ligacao_dir(pasta / "skills" / "emprestada", fora)
        self.recusa_no_candidato(pasta, "ligação")

    def test_arquivo_ligado_recusa(self):
        fora = self.canario()
        pasta = self.candidato()
        self.link_de_arquivo(pasta / "skills" / "ola" / "nota.md", fora / "nota.md")
        self.recusa_no_candidato(pasta, "ligação")

    def test_vinculo_fisico_recusa(self):
        fora = self.canario()
        pasta = self.candidato()
        self.vinculo(pasta / "skills" / "ola" / "nota.md", fora / "nota.md")
        self.recusa_no_candidato(pasta, "vínculo físico")

    def test_a_pasta_do_candidato_ligada_recusa(self):
        real = self.candidato()
        ligada = self.proj / "plugins-candidatos" / "demo-ligado"
        criar_ligacao_dir(ligada, real)
        for funcao in (MOD.conferir, MOD.manifesto, MOD.revisar):
            with self.subTest(funcao=funcao.__name__), self.assertRaises(MOD.CandidatoRecusado):
                funcao(ligada)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO só no POSIX")
    def test_fifo_recusa_sem_travar(self):
        pasta = self.candidato()
        self.fifo(pasta / "skills" / "ola" / "fila.md")
        self.recusa_no_candidato(pasta, "não é arquivo comum")

    def test_pasta_de_candidatos_trocada_por_ligacao_recusa(self):
        # Contratos §5 ("origem ... sem ligação") e revisão do pacote PLUGINS: o conferir só olhava a pasta do
        # candidato para baixo; uma plugins-candidatos/ trocada por junção mudava o candidato em silêncio.
        real = self.candidato()
        fora = self.base / "candidatos-de-fora"
        fora.mkdir()
        os.rename(real, fora / real.name)
        (self.proj / "plugins-candidatos").rmdir()
        criar_ligacao_dir(self.proj / "plugins-candidatos", fora)
        ligado = self.proj / "plugins-candidatos" / real.name
        for funcao in (MOD.conferir, MOD.manifesto, MOD.revisar):
            with self.subTest(funcao=funcao.__name__), self.assertRaises(MOD.CandidatoRecusado) as ctx:
                funcao(ligado)
            self.assertIn("passa por ligação", str(ctx.exception))
        self.assertTrue(MOD.conferir(fora / real.name)["conforme"], "fora do lugar padrão, a cópia é só lida")

    def test_projeto_ligado_recusa_no_conferir(self):
        fora = self.canario()
        escrever(self.outro / "plugins-candidatos" / "ligado-kit",
                 {".claude-plugin/plugin.json": '{"name": "ligado-kit", "description": "X."}',
                  "skills/ola/SKILL.md": SKILL_OK, "skills/ola/nota.md": (fora / "nota.md").read_text("utf-8")})
        criar_ligacao_dir(self.raiz / "projects" / "ligado", self.outro)
        pasta = self.raiz / "projects" / "ligado" / "plugins-candidatos" / "ligado-kit"
        for funcao in (MOD.conferir, MOD.manifesto, MOD.revisar):
            with self.subTest(funcao=funcao.__name__), self.assertRaises(MOD.CandidatoRecusado) as ctx:
                funcao(pasta)
            self.assertNotIn("CANARIO", str(ctx.exception.motivos))

    def test_sessao_nao_le_outro_projeto_por_ligacao(self):
        # A trava da sessão segue o caminho real: uma junção dentro de projects/demo para projects/outro recusa.
        fora = self.canario()
        criar_ligacao_dir(self.proj / "atalho", fora)
        os.environ[VARIAVEL_PROJETO], os.environ[VARIAVEL_RAIZ] = "demo", str(self.raiz)
        for funcao in (MOD.conferir, MOD.revisar):
            with self.subTest(funcao=funcao.__name__), self.assertRaises(MOD.CandidatoRecusado) as ctx:
                funcao(self.proj / "atalho")
            self.assertNotIn("CANARIO", str(ctx.exception.motivos))
        del os.environ[VARIAVEL_RAIZ]
        with self.assertRaises(MOD.CandidatoRecusado):
            MOD.conferir(self.proj / "atalho")

    def test_sessao_cujo_projeto_e_juncao_para_outro_recusa(self):
        # Reconferência do pacote PLUGINS: com a raiz, o realpath de projects/<p> também era resolvido, e um
        # projects/ligado trocado por junção para projects/outro deixava ler o outro projeto.
        importado = self.outro / "importado" / ".claude"
        escrever(importado, {"skills/x/SKILL.md": SKILL_OK, "skills/x/nota.md": CANARIO + "\n"})
        criar_ligacao_dir(self.raiz / "projects" / "ligado", self.outro)
        os.environ[VARIAVEL_PROJETO], os.environ[VARIAVEL_RAIZ] = "ligado", str(self.raiz)
        for funcao in (MOD.conferir, MOD.revisar):
            with self.subTest(funcao=funcao.__name__), self.assertRaises(MOD.CandidatoRecusado) as ctx:
                funcao(self.raiz / "projects" / "ligado" / "importado" / ".claude")
            self.assertNotIn("CANARIO", str(ctx.exception.motivos))


class TestLigacoesNaOrigem(Ligacoes, unittest.TestCase):
    def origem(self):
        origem = self.proj / "importado" / ".claude"
        escrever(origem, {"skills/ola/SKILL.md": SKILL_OK, "skills/ola/referencias/guia.md": "Guia fictício.\n"})
        return origem

    def recusa_ao_montar(self, origem, trecho):
        with self.assertRaises(MOD.CandidatoRecusado) as ctx:
            MOD.montar(self.raiz, "demo", "kit", origem)
        self.assertTrue(any(trecho in m for m in ctx.exception.motivos), ctx.exception.motivos)
        self.assertNotIn("CANARIO", str(ctx.exception.motivos))
        self.nada_montado()

    def test_pasta_ligada_na_origem_recusa(self):
        fora = self.canario()
        origem = self.origem()
        criar_ligacao_dir(origem / "skills" / "ola" / "atalho", fora)
        self.recusa_ao_montar(origem, "ligação")

    def test_arquivo_ligado_na_origem_recusa(self):
        fora = self.canario()
        origem = self.origem()
        self.link_de_arquivo(origem / "skills" / "ola" / "nota.md", fora / "nota.md")
        self.recusa_ao_montar(origem, "ligação")

    def test_vinculo_fisico_na_origem_recusa(self):
        fora = self.canario()
        origem = self.origem()
        self.vinculo(origem / "skills" / "ola" / "nota.md", fora / "nota.md")
        self.recusa_ao_montar(origem, "vínculo físico")

    def test_componente_da_raiz_da_origem_ligado_recusa(self):
        fora = self.canario()
        origem = self.proj / "importado"
        origem.mkdir()
        criar_ligacao_dir(origem / "skills", fora.parent)
        self.recusa_ao_montar(origem, "ligação")

    def test_skill_avulsa_com_skill_md_ligado_recusa(self):
        fora = self.canario()
        origem = self.proj / "trazida"
        origem.mkdir()
        self.link_de_arquivo(origem / "SKILL.md", fora / "SKILL.md")
        self.recusa_ao_montar(origem, "ligação")

    def test_origem_por_caminho_ligado_recusa(self):
        fora = self.canario()
        criar_ligacao_dir(self.proj / "atalho", fora.parent)
        self.recusa_ao_montar(self.proj / "atalho" / fora.name, "passa por ligação")

    def test_pasta_de_candidatos_ligada_para_data_recusa(self):
        origem = self.origem()
        alvo = self.proj / "data" / "copia"
        alvo.mkdir(parents=True)
        criar_ligacao_dir(self.proj / "plugins-candidatos", alvo)
        with self.assertRaises(MOD.CandidatoRecusado) as ctx:
            MOD.montar(self.raiz, "demo", "kit", origem)
        self.assertIn("ligação", str(ctx.exception))
        self.assertEqual(list(alvo.iterdir()), [])

    def test_projeto_ligado_recusa(self):
        fora = self.canario()
        criar_ligacao_dir(self.raiz / "projects" / "ligado", self.outro)
        with self.assertRaises(MOD.CandidatoRecusado):
            MOD.montar(self.raiz, "ligado", "kit", self.raiz / "projects" / "ligado" / fora.name)
        self.assertFalse((self.outro / "plugins-candidatos").exists())

    def test_limpeza_do_temporario_tira_a_ligacao_e_nao_o_alvo(self):
        # O `shutil.rmtree` do Windows pode descer por junção; a limpeza do montar tira só o nome da ligação.
        fora = self.canario()
        temp = self.proj / "plugins-candidatos" / ".montando-teste"
        escrever(temp, {"skills/ola/SKILL.md": SKILL_OK})
        criar_ligacao_dir(temp / "skills" / "atalho", fora)
        MOD._apagar_sem_seguir(temp)
        self.assertFalse(os.path.lexists(temp))
        self.assertEqual((fora / "nota.md").read_text(encoding="utf-8"), CANARIO + "\n")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO só no POSIX")
    def test_fifo_na_origem_recusa_sem_travar(self):
        origem = self.origem()
        self.fifo(origem / "skills" / "ola" / "fila.md")
        self.recusa_ao_montar(origem, "não é arquivo comum")


if __name__ == "__main__":
    unittest.main()
