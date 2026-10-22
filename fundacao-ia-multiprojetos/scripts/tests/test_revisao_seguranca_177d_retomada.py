"""Revisão de segurança da 1.7.7, quarta passada — o próprio arquivo da RETOMADA (R177D-2).

- R177D-2 (baixa, desde a 1.7.6): a RETOMADA conferia só a pasta, e o arquivo era reescrito no lugar. `arquivar
  --arquivo <pasta comum>/.env` (ou `.credentials.json`, `secrets`, `chave.pem`) copiava o conteúdo inteiro para o
  histórico e inseria o ponteiro no original; com a RETOMADA como vínculo físico de `.ssh/id_ed25519`, a chave era
  alterada. Agora o nome do arquivo passa pela mesma regra antes de qualquer leitura (a mesma resposta exista ele ou
  não), a RETOMADA é lida sem seguir ligação, sem vínculo físico (no lstat e, depois de abrir, no fstat) e com teto, e
  é reescrita por temporário e troca de nome (`gravacao_segura.publicar`), nunca através do nome.

Pastas descartáveis com estrutura fictícia (o apoio de test_revisao_seguranca_177d_validadores.py). Cada teste falha
no HEAD revisado (59b3813) e passa depois da correção; os controles mostram o uso legítimo.
"""

from __future__ import annotations

import os
import types
import unittest
from unittest import mock

from test_auditoria_1_7_6_validadores import SEGREDO, carregar, link_de_arquivo, sha_de
from test_revisao_seguranca_177d_validadores import _Fundacoes

# O nome que existe e um da mesma regra que não existe: a resposta não pode dizer qual é qual.
NOMES = ((".env", ".env.nao-existe"), (".credentials.json", "nao-existe.credentials.json"),
         ("secrets", "secrets-nao-existe"), ("chave.pem", "nao-existe.pem"))


class TestRetomadaDeNomeProtegidoOuVinculo(_Fundacoes):
    """R177D-2: o próprio arquivo da RETOMADA passa pela regra, sem seguir ligação nem vínculo físico."""

    def conteudo(self) -> str:
        return self.texto_retomada([], [f"- Item {SEGREDO}: não deveria ser copiado"])

    def test_nome_protegido_recusado_antes_de_ler_exista_ou_nao(self):
        comum = self.base / "comum"  # pasta sem raiz de fundação acima
        comum.mkdir()
        raiz = self.fundacao("Users", "Titular", "Projeto de IA")
        for pasta in (comum, raiz):
            for nome, ausente in NOMES:
                with self.subTest(pasta=pasta.name, nome=nome):
                    arq = pasta / nome
                    arq.write_text(self.conteudo(), encoding="utf-8")
                    antes = sha_de(arq)
                    respostas = []
                    for alvo in (arq, pasta / ausente):
                        codigo, res, saida = self.json_de("retomada.py", "validar", "--arquivo", alvo, timeout=60)
                        self.assertEqual(codigo, 1, res)  # no 59b3813: código 0, com o arquivo lido
                        self.assertNotIn(SEGREDO, saida)
                        respostas.append(res)
                    self.assertEqual(respostas[0], respostas[1], "a resposta diz se o arquivo existe")
                    self.assertIn("nada foi lido", respostas[0]["erro"])
                    codigo, res, _ = self.json_de("retomada.py", "arquivar", "--arquivo", arq, "--historico",
                                                  pasta / "hist", timeout=60)
                    self.assertEqual(codigo, 1, res)
                    self.assertEqual(sha_de(arq), antes, "o arquivo de nome protegido foi reescrito")
                    self.assertFalse((pasta / "hist").exists(), "o conteúdo foi copiado para o histórico")

    def test_vinculo_fisico_e_link_para_chave_recusados(self):
        ssh, proj = self.base / "home" / ".ssh", self.base / "proj"
        ssh.mkdir(parents=True)
        proj.mkdir()
        chave = ssh / "id_ed25519"
        chave.write_text(self.conteudo(), encoding="utf-8")
        antes = sha_de(chave)
        try:
            os.link(chave, proj / "RETOMADA.md")
        except (OSError, NotImplementedError) as exc:  # sistema de arquivos sem vínculo físico (FAT, exFAT)
            raise unittest.SkipTest(f"vínculo físico indisponível aqui: {exc}") from None
        casos = {"vínculo físico": proj / "RETOMADA.md"}
        if link_de_arquivo(proj / "LIGADA.md", chave):
            casos["ligação"] = proj / "LIGADA.md"
        for motivo, arq in casos.items():
            with self.subTest(caso=motivo):
                codigo, res, saida = self.json_de("retomada.py", "validar", "--arquivo", arq, timeout=60)
                self.assertEqual(codigo, 1, res)
                self.assertIn(motivo, res["erro"])
                codigo, res, saida = self.json_de("retomada.py", "arquivar", "--arquivo", arq, "--historico",
                                                  proj / "hist", timeout=60)
                self.assertEqual(codigo, 1, res)  # no 59b3813: código 0, a chave copiada e reescrita
                self.assertNotIn(SEGREDO, saida)
                self.assertEqual(sha_de(chave), antes, "a chave de .ssh foi alterada pela RETOMADA")
                self.assertFalse((proj / "hist").exists(), "a chave foi copiada para o histórico")

    def test_fstat_depois_de_abrir_tambem_confere_o_vinculo(self):
        mod = carregar("retomada")
        arq = self.base / "proj" / "RETOMADA.md"
        arq.parent.mkdir()
        arq.write_text(self.conteudo(), encoding="utf-8")
        try:
            os.link(arq, arq.with_name("outro-nome.md"))
        except (OSError, NotImplementedError) as exc:
            raise unittest.SkipTest(f"vínculo físico indisponível aqui: {exc}") from None
        real = os.lstat

        def lstat_de_um_nome(p, *a, **k):  # o vínculo aparece só depois do lstat (corrida): o fstat pega
            st = real(p, *a, **k)
            return types.SimpleNamespace(st_mode=st.st_mode, st_nlink=1, st_dev=st.st_dev, st_ino=st.st_ino,
                                         st_size=st.st_size, st_reparse_tag=getattr(st, "st_reparse_tag", 0))

        with mock.patch.object(mod.os, "lstat", lstat_de_um_nome):
            with self.assertRaises(mod.VinculoFisico):
                mod.ler_retomada(arq)

    def test_controle_retomada_comum_e_reescrita_por_troca_de_nome(self):
        comum = self.base / "comum"
        comum.mkdir()
        arq = comum / "RETOMADA.md"
        arq.write_bytes(self.texto_retomada([], self.ITENS).replace("\n", "\r\n").encode("utf-8"))  # CRLF
        codigo, res, _ = self.json_de("retomada.py", "validar", "--arquivo", arq, timeout=60)
        self.assertEqual(codigo, 0, res)
        codigo, res, _ = self.json_de("retomada.py", "arquivar", "--arquivo", arq, "--historico", comum / "hist",
                                      timeout=60)
        self.assertEqual(codigo, 0, res)
        self.assertIn("Histórico arquivado: hist/", arq.read_text(encoding="utf-8"))
        self.assertEqual(os.lstat(arq).st_nlink, 1)
        codigo, res, _ = self.json_de("retomada.py", "validar", "--arquivo", arq, timeout=60)
        self.assertEqual((codigo, [h["estado"] for h in res["historicos"]]), (0, ["conferido"]))


if __name__ == "__main__":
    unittest.main()
