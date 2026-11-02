"""Revisão de segurança da 1.7.10, CI-F8: `verificar_pacote.py --lista-so-cresce` com merges na história da lista.

O `git log -- <lista>` simplifica a história: o merge igual a um dos pais segue só esse pai, e os commits do outro lado
somem do log. Assim passavam (lista vazia de problemas) o merge -s ours que descarta a linha acrescentada num ramo
lateral, o -X theirs que troca o hash já liberado na linha principal e o merge com um ramo aberto antes de a lista
existir, que troca a linha mais antiga (as três formas do achado e do cético 1). Com `git log --full-history`, toda
versão da lista na história do HEAD é conferida; o merge que leva todas as linhas continua passando.
Repositórios temporários, sem rede; nada da entrega real é tocado.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ENTREGA = Path(__file__).resolve().parents[1]
NOME = "fundacao-ia-multiprojetos"
PACOTE, COMPLETO = f"{NOME}.skill", f"{NOME}-completo.zip"
HISTORICO = "HISTORICO-PACOTES-SHA256.txt"


def carregar_verificador():
    spec = importlib.util.spec_from_file_location("verificar_pacote_lista_com_merge", ENTREGA / "verificar_pacote.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # só define constantes e funções
    return mod


def linha(letra: str, versao: str, arquivo: str = PACOTE) -> str:
    return f"{letra * 64}  {versao}/{arquivo}"


def apagar(pasta: Path) -> None:
    """Apaga a pasta do ensaio. No Windows, o git grava os objetos só de leitura, e o rmtree deixava a pasta inteira
    no %TEMP%: os arquivos voltam a aceitar escrita antes."""
    for raiz, _pastas, arquivos in os.walk(pasta):
        for nome in arquivos:
            os.chmod(os.path.join(raiz, nome), stat.S_IREAD | stat.S_IWRITE)
    shutil.rmtree(pasta, ignore_errors=True)


class TestListaSoCresceComMerge(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="seg-1710-lista-"))
        self.addCleanup(apagar, self.base)
        self.repo = self.base / "repo"
        (self.repo / "entrega").mkdir(parents=True)
        self.lista = self.repo / "entrega" / HISTORICO
        self.git("init", "-q")
        self.git("symbolic-ref", "HEAD", "refs/heads/principal")  # o nome do ramo não depende da configuração
        self.vp = carregar_verificador()

    def git(self, *args: str, falha_ok: bool = False) -> str:
        config = ("user.name=ensaio", "user.email=ensaio-sem-email", "commit.gpgsign=false", "core.autocrlf=false",
                  "merge.ff=true", "core.hooksPath=" + str(self.base / "sem-hooks"))  # sem e-mail no texto
        r = subprocess.run(["git", "-C", str(self.repo), *(x for c in config for x in ("-c", c)), *args],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if not falha_ok:
            self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def gravar(self, *linhas: str, mensagem: str = "lista") -> str:
        """Grava a lista com estas linhas, faz o commit e devolve o hash dele."""
        self.lista.parent.mkdir(exist_ok=True)  # o checkout de um ramo sem a lista leva a pasta vazia
        self.lista.write_text("".join(x + "\n" for x in linhas), encoding="utf-8", newline="\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", mensagem)
        return self.git("rev-parse", "HEAD").strip()

    def assert_reprova_pelo_commit(self, commit: str) -> None:
        problemas = self.vp.conferir_crescimento(self.lista)
        self.assertTrue(any("só cresce" in p and commit[:12] in p for p in problemas), problemas)

    def test_merge_s_ours_que_descarta_a_linha_do_ramo_lateral_reprova(self):
        """r1 (O39, O40): o ramo lateral acrescenta 1.0.1 e o merge -s ours fica com a lista da linha principal."""
        a = linha("a", "1.0.0")
        self.gravar(a, mensagem="v1")
        self.git("checkout", "-q", "-b", "lateral")
        lateral = self.gravar(a, linha("b", "1.0.1"), mensagem="lateral acrescenta a linha b")
        self.git("checkout", "-q", "principal")
        self.git("merge", "-q", "--no-ff", "-s", "ours", "--no-edit", "lateral")
        self.assertEqual(self.lista.read_text(encoding="utf-8"), a + "\n")
        self.assert_reprova_pelo_commit(lateral)

    def test_merge_de_varios_ramos_que_descarta_as_linhas_deles_reprova(self):
        """A mesma simplificação no merge de vários ramos de uma vez (-s ours com dois ramos laterais)."""
        a = linha("a", "1.0.0")
        self.gravar(a, mensagem="v1")
        laterais = []
        for nome, letra in (("lateral1", "b"), ("lateral2", "c")):
            self.git("checkout", "-q", "-b", nome, "principal")
            laterais.append(self.gravar(a, linha(letra, "1.0.1"), mensagem=f"{nome} acrescenta a linha {letra}"))
        self.git("checkout", "-q", "principal")
        self.git("merge", "-q", "--no-ff", "-s", "ours", "--no-edit", "lateral1", "lateral2")
        self.assertEqual(self.lista.read_text(encoding="utf-8"), a + "\n")
        for commit in laterais:
            self.assert_reprova_pelo_commit(commit)

    def test_merge_x_theirs_que_troca_o_hash_liberado_na_principal_reprova(self):
        """r2 (cético 1, A5): a principal libera 1.0.1 com o hash b; o merge -X theirs fica com o c do ramo lateral."""
        a = linha("a", "1.0.0")
        self.gravar(a, mensagem="v1")
        self.git("checkout", "-q", "-b", "lateral")
        self.gravar(a, linha("c", "1.0.1"), mensagem="lateral com outro hash para 1.0.1")
        self.git("checkout", "-q", "principal")
        liberado = self.gravar(a, linha("b", "1.0.1"), mensagem="principal libera 1.0.1 (hash b)")
        self.git("merge", "-q", "-X", "theirs", "--no-edit", "lateral")
        self.assertIn(linha("c", "1.0.1"), self.lista.read_text(encoding="utf-8"))
        self.assert_reprova_pelo_commit(liberado)

    def test_merge_com_ramo_aberto_antes_da_lista_que_troca_a_linha_mais_antiga_reprova(self):
        """r3 (cético 1, A5): o ramo aberto antes de a lista existir cria outra com a 1.0.0 de outro hash."""
        (self.repo / "LEIA-ME.txt").write_text("ensaio\n", encoding="utf-8", newline="\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "início")
        self.git("branch", "antigo")
        criada = self.gravar(linha("a", "1.0.0"), mensagem="cria a lista (1.0.0 hash a)")
        self.git("checkout", "-q", "antigo")
        self.gravar(linha("d", "1.0.0"), mensagem="ramo antigo cria a lista com outro hash")
        self.git("checkout", "-q", "principal")
        self.git("merge", "-q", "-X", "theirs", "--no-edit", "antigo", falha_ok=True)
        if self.git("ls-files", "-u"):  # conflito de criação dos dois lados: fica com o lado do ramo antigo
            self.git("checkout", "--theirs", "--", f"entrega/{HISTORICO}")
            self.git("add", "-A")
            self.git("commit", "-q", "--no-edit")
        self.assertEqual(self.lista.read_text(encoding="utf-8"), linha("d", "1.0.0") + "\n")
        self.assert_reprova_pelo_commit(criada)

    def test_merges_que_levam_todas_as_linhas_passam(self):
        """O uso normal continua: ramos que só acrescentam, unidos por merge (com e sem conflito), passam."""
        a, b, c = linha("a", "1.0.0"), linha("b", "1.0.0", COMPLETO), linha("c", "1.0.1")
        self.gravar(a, mensagem="v1")
        self.git("checkout", "-q", "-b", "lateral")
        self.gravar(a, b, mensagem="lateral acrescenta b")
        self.git("checkout", "-q", "principal")
        (self.repo / "LEIA-ME.txt").write_text("ensaio\n", encoding="utf-8", newline="\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "outro arquivo")
        self.git("merge", "-q", "--no-edit", "lateral")
        self.assertEqual(self.vp.conferir_crescimento(self.lista), [])
        self.git("checkout", "-q", "-b", "outro")
        self.gravar(a, b, c, mensagem="outro acrescenta c")
        self.git("checkout", "-q", "principal")
        self.gravar(a, b, linha("e", "1.0.2"), mensagem="principal acrescenta e")
        self.git("merge", "-q", "--no-edit", "outro", falha_ok=True)  # conflito: as duas pontas acrescentam
        self.gravar(a, b, c, linha("e", "1.0.2"), mensagem="merge com as linhas dos dois lados")
        self.assertEqual(len(self.git("rev-list", "--merges", "HEAD").split()), 2)
        self.assertEqual(self.vp.conferir_crescimento(self.lista), [])

    # Endurecimento da revisão 1 do CI-F8 (rodada 4): a história conferida é a dos objetos gravados.
    def sumir(self, objeto: str) -> None:
        caminho = self.repo / ".git" / "objects" / objeto[:2] / objeto[2:]
        os.chmod(caminho, stat.S_IREAD | stat.S_IWRITE)
        caminho.unlink()

    def test_commit_trocado_por_git_replace_nao_esconde_a_versao_antiga(self):
        """O `git replace` troca o v1 por um commit com a lista do v2: o log comum deixa de ver a remoção do hash a."""
        v1 = self.gravar(linha("a", "1.0.0"), mensagem="v1")
        v2 = self.gravar(linha("b", "1.0.0"), mensagem="v2 troca o hash de 1.0.0")
        falso = self.git("commit-tree", f"{v2}^{{tree}}", "-m", "falso").strip()
        self.git("replace", v1, falso)
        self.assertEqual(self.git("show", f"{v1}:entrega/{HISTORICO}"), linha("b", "1.0.0") + "\n")  # a troca vale
        self.assert_reprova_pelo_commit(v1)

    def test_grafts_nao_escondem_a_versao_antiga(self):
        """O arquivo de grafts tira o pai do v2: o log comum deixa de ver o v1 (no git 2.43 e no 2.56, que ainda leem
        o arquivo, com aviso de obsoleto; sem esse suporte, não há o que esconder, e a conferência reprova do mesmo
        jeito)."""
        v1 = self.gravar(linha("a", "1.0.0"), mensagem="v1")
        v2 = self.gravar(linha("b", "1.0.0"), mensagem="v2 troca o hash de 1.0.0")
        (self.repo / ".git" / "info").mkdir(exist_ok=True)
        (self.repo / ".git" / "info" / "grafts").write_text(v2 + "\n", encoding="utf-8", newline="\n")
        self.assert_reprova_pelo_commit(v1)

    def test_versao_ou_historia_que_o_git_nao_le_reprova(self):
        """Sem o blob da lista no v1, o git show falha; sem o objeto do v1, o git log falha. Antes, as duas falhas
        valiam como "sem versão" e a conferência passava com a lista vazia de problemas."""
        v1 = self.gravar(linha("a", "1.0.0"), mensagem="v1")
        self.gravar(linha("b", "1.0.0"), mensagem="v2 troca o hash de 1.0.0")
        self.sumir(self.git("rev-parse", f"{v1}:entrega/{HISTORICO}").strip())
        problemas = self.vp.conferir_crescimento(self.lista)
        self.assertTrue(any(f"não leu a lista do commit {v1[:12]}" in p for p in problemas), problemas)
        self.sumir(v1)
        problemas = self.vp.conferir_crescimento(self.lista)
        self.assertTrue(any("não leu a história da lista" in p for p in problemas), problemas)

    def test_repositorio_sem_commit_reprova_com_mensagem_propria(self):
        """Faltou do revisor 2 na revisão 2 do CI-F8: sem commit, o git log falhava com o código 128 e a mensagem era
        a de falha do git (antes da revisão 1, passava com a lista vazia de problemas). A lista no índice não muda
        isso."""
        self.lista.write_text(linha("a", "1.0.0") + "\n", encoding="utf-8", newline="\n")
        for etapa in ("só na pasta", "no índice"):
            with self.subTest(etapa=etapa):
                problemas = self.vp.conferir_crescimento(self.lista)
                self.assertEqual(len(problemas), 1, problemas)
                self.assertIn("ainda não tem commit", problemas[0])
            self.git("add", "-A")

    def test_log_follow_e_show_signature_na_configuracao_global_nao_escondem_o_ramo(self):
        """Faltou do revisor 1 na revisão 2 do CI-F8: a etapa 03 roda na máquina do titular, com a configuração global
        dele. Com log.follow e log.showSignature ligados (por GIT_CONFIG_GLOBAL, um arquivo do ensaio), o merge -s ours
        continua reprovando (medido no git 2.56 e no 2.43 em 01/11/2026)."""
        configuracao = self.base / "global.gitconfig"
        configuracao.write_text("[log]\n\tfollow = true\n\tshowSignature = true\n", encoding="utf-8", newline="\n")
        with mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(configuracao)}):
            a = linha("a", "1.0.0")
            self.gravar(a, mensagem="v1")
            self.git("checkout", "-q", "-b", "lateral")
            lateral = self.gravar(a, linha("b", "1.0.1"), mensagem="lateral acrescenta a linha b")
            self.git("checkout", "-q", "principal")
            self.git("merge", "-q", "--no-ff", "-s", "ours", "--no-edit", "lateral")
            self.assertEqual(self.git("config", "--global", "log.follow").strip(), "true")  # a configuração vale
            self.assert_reprova_pelo_commit(lateral)

    def test_lista_apagada_e_recriada_continua_passando(self):
        """O commit que apagou a lista não a tem (o git show falha e o ls-tree não a lista): não reprova sozinho."""
        a = linha("a", "1.0.0")
        self.gravar(a, mensagem="v1")
        self.lista.unlink()
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "apaga a lista")
        self.gravar(a, linha("b", "1.0.1"), mensagem="recria a lista com as linhas")
        self.assertEqual(self.vp.conferir_crescimento(self.lista), [])


if __name__ == "__main__":
    unittest.main()
