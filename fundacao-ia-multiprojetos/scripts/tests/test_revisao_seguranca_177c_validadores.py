"""Revisão de segurança da 1.7.7, terceira passada — o `--base` da matriz e a pasta da RETOMADA dentro de pasta negada
fora de qualquer raiz de fundação (R177C-B-01).

A recusa de caminho protegido olhava as partes relativas à base e, desde a segunda passada, o caminho inteiro relativo a
cada raiz de fundação acima dele; fora de qualquer raiz, quem escolhia a base escolhia o que era protegido. Com
`--base <home>/.ssh`, a linha `id_ed25519` (ou `fundacao_titular`, nome que a lista não tem) saía "conferida" quando a
versão avaliada era um trecho da chave e "não cita a versão" quando não — o oráculo de conteúdo de volta; a RETOMADA
dentro de `.ssh` conferia o hash de qualquer arquivo de lá ("conferido" ou "alterado") e entregava os itens do
histórico, e o `arquivar` gravava ali. Agora a base, a pasta da RETOMADA e o destino do histórico cujo caminho real
passa por nome da lista de negação dos perfis do host (`.ssh`, `.codex`, `secrets`...) ou por nome curto 8.3, em
qualquer parte e comparado como o Windows compara, são recusados antes de qualquer consulta dentro deles, com a mesma
resposta exista ou não o alvo.

HOME falso numa pasta descartável (o apoio de test_auditoria_1_7_6_validadores.py); a "chave" é texto fictício. Cada
teste falha no HEAD revisado (db7e68e) e passa depois da correção; os controles mostram o uso legítimo.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

import test_auditoria_1_7_6_validadores as base_176  # o módulo, não as classes: os testes dela não rodam de novo aqui
from apoio import criar_ligacao_dir, rodar_script
from test_auditoria_1_7_6_validadores import SEGREDO, _Pastas, carregar, sha_de

MATRIZ, RETOMADA = base_176.TestMatrizEvidencia.__dict__, base_176.TestRetomadaHistorico.__dict__  # os ajudantes
# A "chave" fictícia só precisa citar a versão das linhas e trazer o canário; sem cabeçalho de chave privada, que a
# varredura de segredos do pacote recusaria (test_pacote_sem_segredo_aparente.py).
CHAVE = f"conteúdo fictício no lugar de uma chave: kit 1.4.1 {SEGREDO}\n"
OUTRO = "texto que não está em arquivo nenhum"  # a versão que não é citada: a resposta não pode mudar com ela
RECUSA = "nada foi lido"
NEGADOS = ("C:/Users/x/.ssh", "/home/x/.SSH/sub", "/home/x/.ssh./sub", "/home/x/.ssh /sub", "/home/x/SSH~1",
           "/srv/Secrets/a", "/x/.codex", "/x/minhas-credentials/y", "/x/.env.local/y", "/x/chave.PEM/y")
LIVRES = ("C:/Users/x/Projeto de IA", "/home/x/fundacao/projects/a/evidence", "/x/state/y", "/x/projects/b/data",
          "/x/ssh-notas/y", "/home/x/fundacao/registry")


class _HomeFalso(_Pastas):
    """HOME falso com `.ssh` (duas "chaves" que citam a versão das linhas), ao lado da fundação fictícia."""

    def setUp(self):
        super().setUp()
        (self.raiz / "registry").mkdir()
        self.home = self.base / "home-falso"
        self.ssh = self.home / ".ssh"
        self.ssh.mkdir(parents=True)
        for nome in ("id_ed25519", "fundacao_titular"):
            (self.ssh / nome).write_text(CHAVE, encoding="utf-8")

    def segredo_em(self, pasta: Path, nome: str) -> Path:
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / nome).write_text(CHAVE, encoding="utf-8")
        return pasta


class TestBaseEmPastaNegada(_HomeFalso):
    """O `--base` (ou a base padrão) em pasta negada fora de qualquer raiz: nada é lido, e a resposta não muda."""

    matriz, ativo, problemas = MATRIZ["matriz"], MATRIZ["ativo"], MATRIZ["problemas"]

    def validar(self, linhas: dict, onde: Path, base: Path | None = None) -> tuple[int, dict, str]:
        mat = self.matriz(linhas, onde)
        p = rodar_script("matriz.py", "validar", "--matriz", mat, *(["--base", base] if base else []), timeout=120)
        try:
            return p.returncode, json.loads(p.stdout), p.stdout
        except ValueError:
            self.fail("saída não é JSON: " + p.stdout[-400:] + p.stderr[-400:])

    def respostas(self, rel: str, onde: Path, base: Path | None = None) -> set[str]:
        """A resposta da linha com a versão citada no arquivo e com a que não é: sem oráculo, as duas são iguais."""
        vistas = set()
        for versao in ("kit 1.4.1", OUTRO):
            codigo, dados, saida = self.validar({"R12": self.ativo(rel, versao)}, onde, base)
            self.assertEqual(codigo, 1, dados)
            self.assertEqual(dados["evidencias"]["conferidas"], [], "a base em pasta negada leu a evidência")
            self.assertNotIn(SEGREDO, saida)
            vistas.add(self.problemas(dados)["R12"])
        return vistas

    def test_base_em_pasta_negada_fora_de_raiz_nao_e_oraculo(self):
        casos = ((self.ssh, "id_ed25519"), (self.ssh, "fundacao_titular"),
                 (self.segredo_em(self.home / ".codex", "config.toml"), "config.toml"),
                 (self.segredo_em(self.home / "secrets", "x.md"), "x.md"),
                 (self.segredo_em(self.home / "Minhas-Credentials", "y.md"), "y.md"))
        for base, rel in casos:
            for onde in (self.raiz / "projects" / "a" / "outputs" / "m.csv", self.fora / "m.csv"):
                with self.subTest(base=base.name, rel=rel, matriz=onde.parent.name):
                    vistas = self.respostas(rel, onde, base)
                    self.assertEqual(len(vistas), 1, f"a resposta varia com o conteúdo: {vistas}")
                    self.assertIn(RECUSA, vistas.pop())

    def test_mesma_resposta_exista_ou_nao_o_alvo_ou_a_base(self):
        linhas = {"R12": self.ativo("id_ed25519"), "R13": self.ativo("nao-existe"),
                  "R14": self.ativo("sub/nao-existe.md")}
        mensagens = set()
        for base in (self.ssh, self.home / "outro" / ".ssh", self.home / "SSH~1", self.home / ".SSH."):
            with self.subTest(base=base.name):
                codigo, dados, _ = self.validar(linhas, self.fora / "m.csv", base)
                self.assertEqual(codigo, 1, dados)
                self.assertEqual(dados["evidencias"]["conferidas"], [], "a base em pasta negada leu a evidência")
                probs = self.problemas(dados)
                mensagens |= {probs[r].split(":", 1)[1].replace(linhas[r]["caminho_evidencia"], "C") for r in linhas}
        self.assertEqual(len(mensagens), 1, f"a resposta varia com o alvo ou com a base: {mensagens}")
        self.assertIn(RECUSA, mensagens.pop())

    def test_base_padrao_em_pasta_negada(self):
        """Sem `--base`: a matriz dentro de `.ssh` (ou de `.ssh/registry/`) faz de `.ssh` a base."""
        for onde in (self.ssh / "m.csv", self.ssh / "registry" / "m.csv"):
            with self.subTest(matriz=onde.relative_to(self.home).as_posix()):
                vistas = self.respostas("id_ed25519", onde)
                self.assertEqual(len(vistas), 1, f"a resposta varia com o conteúdo: {vistas}")
                self.assertIn(RECUSA, vistas.pop())

    def test_base_por_ligacao_para_pasta_negada(self):
        atalho = self.home / "atalho"
        tipo = criar_ligacao_dir(atalho, self.ssh)
        vistas = self.respostas("id_ed25519", self.fora / "m.csv", atalho)
        self.assertEqual(len(vistas), 1, f"{tipo}: a resposta varia com o conteúdo: {vistas}")
        self.assertIn(RECUSA, vistas.pop())

    def test_decisao_antes_de_consultar_a_base_e_o_alvo(self):
        mod = carregar("matriz")
        with mock.patch.object(mod, "raizes_acima", side_effect=AssertionError("consultou o disco dentro da base")):
            self.assertIn("nega", mod.base_recusada(self.ssh, self.fora / "m.csv") or "")
        with mock.patch.object(mod, "examinar", side_effect=AssertionError("tocou o alvo")), \
                mock.patch.object(mod, "blocos", side_effect=AssertionError("leu o alvo")):
            for rel in ("id_ed25519", "nao-existe", "sub/x.md"):
                with self.subTest(rel=rel):
                    achados = mod.examinar_evidencia(self.ssh.resolve(), rel, "kit 1.4.1", "")
                    self.assertEqual(len(achados), 1)
                    self.assertIn("protegido", achados[0])

    def test_criterio_reaproveita_a_lista_e_a_comparacao(self):
        matriz, retomada = carregar("matriz"), carregar("retomada")
        self.assertEqual(matriz.NOMES_PROTEGIDOS, retomada.NOMES_PROTEGIDOS)
        for mod in (matriz, retomada):
            for caminho in NEGADOS:
                with self.subTest(modulo=mod.__name__, caminho=caminho):
                    self.assertTrue(mod.caminho_negado(Path(caminho)))
            for caminho in LIVRES:
                with self.subTest(modulo=mod.__name__, caminho=caminho):
                    self.assertFalse(mod.caminho_negado(Path(caminho)))
            with mock.patch.object(mod, "NOMES_PROTEGIDOS", ("*xyz*",)):  # a lista dos perfis, não uma cópia
                self.assertTrue(mod.caminho_negado(Path("/a/ABxyZ./c")))
                self.assertFalse(mod.caminho_negado(Path("/a/.ssh/c")))
                self.assertTrue(mod.protegido(Path("/a"), ["ABxyZ", "c"]))


class TestPastaDaRetomadaNegada(_HomeFalso):
    """A pasta da RETOMADA e o destino do histórico em pasta negada: nada é lido nem gravado."""

    ITENS, texto_retomada, historico = RETOMADA["ITENS"], RETOMADA["texto_retomada"], RETOMADA["historico"]

    def rodar(self, *args) -> tuple[int, dict, str]:
        p = rodar_script("retomada.py", *args, timeout=60)
        try:
            return p.returncode, json.loads(p.stdout), p.stdout
        except ValueError:
            self.fail("saída não é JSON: " + p.stdout[-400:] + p.stderr[-400:])

    def ponteiros(self) -> list[str]:
        h = self.historico(self.ssh / "hist.md", [f"- Item de dentro {SEGREDO}: não deveria aparecer"])
        return [f"Histórico arquivado: hist.md (sha256 {h})",
                f"Histórico arquivado: id_ed25519 (sha256 {sha_de(self.ssh / 'id_ed25519')})",  # o hash certo
                f"Histórico arquivado: id_ed25519 (sha256 {'0' * 64})",                         # o errado
                f"Histórico arquivado: nao-existe.md (sha256 {'0' * 64})"]

    def test_retomada_em_pasta_negada_nao_le_nem_confere(self):
        atalho = self.home / "atalho"
        tipo = criar_ligacao_dir(atalho, self.ssh)
        texto = self.texto_retomada(self.ponteiros(), self.ITENS)
        (self.ssh / "RETOMADA.md").write_text(texto, encoding="utf-8")
        respostas = []
        for arq in (self.ssh / "RETOMADA.md", atalho / "RETOMADA.md", self.ssh / "NAO-EXISTE.md",
                    self.home / "outro" / "secrets" / "RETOMADA.md"):
            with self.subTest(arquivo=arq.relative_to(self.home).as_posix(), ligacao=tipo):
                codigo, res, saida = self.rodar("validar", "--arquivo", arq)
                self.assertEqual(codigo, 1, res)
                self.assertNotIn(SEGREDO, saida, "o validar leu o histórico de dentro da pasta negada")
                for estado in ('"conferido"', '"alterado"'):  # o estado do ponteiro era oráculo do hash
                    self.assertNotIn(estado, saida, "o validar conferiu o hash de um arquivo da pasta negada")
                respostas.append(res)
        self.assertEqual(len({json.dumps(r, sort_keys=True) for r in respostas}), 1,
                         f"a resposta varia com a RETOMADA ou com o alvo: {respostas}")
        self.assertIn(RECUSA, respostas[0]["erro"])

    def test_arquivar_nao_grava_em_pasta_negada(self):
        arq = self.ssh / "RETOMADA.md"
        arq.write_text(self.texto_retomada([], self.ITENS), encoding="utf-8")
        antes, nomes = sha_de(arq), sorted(p.name for p in self.ssh.iterdir())
        for pasta in (self.ssh / "retomada", self.ssh):
            with self.subTest(historico=pasta.relative_to(self.home).as_posix()):
                codigo, res, _ = self.rodar("arquivar", "--arquivo", arq, "--historico", pasta)
                self.assertEqual(codigo, 1, res)
                self.assertFalse(res["ok"])
                self.assertEqual(sha_de(arq), antes, "a RETOMADA dentro da pasta negada foi alterada")
                self.assertEqual(sorted(p.name for p in self.ssh.iterdir()), nomes, "gravou na pasta negada")

    def test_destino_em_pasta_negada_e_ponteiro_recusados_sem_tocar(self):
        mod = carregar("retomada")
        with mock.patch.object(mod, "falha_no_caminho", side_effect=AssertionError("tocou o histórico")), \
                mock.patch.object(mod, "ler_contido", side_effect=AssertionError("leu o histórico")):
            for rel in ("hist.md", "nao-existe.md", "id_ed25519"):
                with self.subTest(rel=rel):
                    self.assertEqual(mod.ler_historico(self.ssh, rel, "0" * 64), (mod.PROTEGIDO, None))
        self.assertTrue(mod.protegido_na_fundacao(self.home, [".ssh", "retomada", "h.md"]))
        self.assertTrue(mod.protegido_na_fundacao(self.ssh, ["retomada", "h.md"]))  # o destino do `arquivar`
        self.assertIn("nega", mod.pasta_recusada(self.ssh / "RETOMADA.md") or "")
        self.assertIsNone(mod.pasta_recusada(self.raiz / "RETOMADA.md"))


class TestControlesLegitimos(_HomeFalso):
    """Uso legítimo: a fundação fictícia dentro do HOME falso que também tem `.ssh` — base padrão, `--base` de projeto,
    RETOMADA com histórico e `arquivar`."""

    matriz, ativo = MATRIZ["matriz"], MATRIZ["ativo"]
    ITENS, texto_retomada = RETOMADA["ITENS"], RETOMADA["texto_retomada"]

    def setUp(self):
        super().setUp()
        self.raiz = self.home / "Projeto de IA"  # a fundação no HOME, como a do titular (nome com espaço)
        (self.raiz / "registry").mkdir(parents=True)

    def test_matriz_na_fundacao_ficticia(self):
        self.escrever("evidence/kit/EVIDENCIAS-A5.md", "Ensaio do kit 1.4.1 (fictício).\n")
        self.escrever("projects/a/evidence/EVIDENCIAS-R60.md", "Python 3.12.10 (fictício).\n")
        linhas = {"R01": self.ativo("evidence/kit/EVIDENCIAS-A5.md"),
                  "R60": self.ativo("projects/a/evidence/EVIDENCIAS-R60.md", "Python 3.12.10")}
        mat = self.matriz(linhas)  # <raiz>/registry/requisitos.csv: a base padrão é a raiz
        for extra in ((), ("--base", self.raiz)):
            with self.subTest(base=extra[1].name if extra else "padrão"):
                p = rodar_script("matriz.py", "validar", "--matriz", mat, *extra, timeout=120)
                dados = json.loads(p.stdout)
                self.assertEqual(p.returncode, 0, dados["erros"])
                self.assertEqual(dados["evidencias"]["conferidas"], ["R01", "R60"])
        mat = self.matriz({"R60": self.ativo("evidence/EVIDENCIAS-R60.md", "Python 3.12.10")},
                          self.raiz / "projects" / "a" / "registry" / "requisitos.csv")
        p = rodar_script("matriz.py", "validar", "--matriz", mat, timeout=120)  # a base padrão é o projeto
        self.assertEqual(json.loads(p.stdout)["evidencias"]["conferidas"], ["R60"], p.stdout[-800:])

    def test_retomada_na_fundacao_ficticia_arquiva_e_valida(self):
        arq = self.raiz / "RETOMADA.md"
        arq.write_text(self.texto_retomada([], self.ITENS), encoding="utf-8")
        p = rodar_script("retomada.py", "arquivar", "--arquivo", arq, "--historico",
                         self.raiz / "evidence" / "retomada", timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        p = rodar_script("retomada.py", "validar", "--arquivo", arq, timeout=60)
        res = json.loads(p.stdout)
        self.assertEqual(p.returncode, 0, res)
        self.assertEqual([h["estado"] for h in res["historicos"]], ["conferido"])


if __name__ == "__main__":
    unittest.main()
