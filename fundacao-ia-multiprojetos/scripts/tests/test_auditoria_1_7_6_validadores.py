"""Auditoria Codex Security da 1.7.6, #7 — validadores que seguiam caminho fora do escopo e ligação de arquivo.

Até a 1.7.6, `matriz.py validar` e `retomada.py validar` aceitavam caminho absoluto ou com `..` e liam o alvo (hash,
versão citada e, na RETOMADA, os itens de "Ações já realizadas" do arquivo de fora); ligação (link simbólico ou junção)
era seguida; a pasta de evidência era percorrida inteira antes do teto de 500 arquivos, e o arquivo, lido sem teto; o
`arquivar` gravava o histórico fora da pasta, com ponteiro absoluto. Cada teste exige o comportamento seguro e falha
na 1.7.6, salvo os controles: o formato real da matriz e da RETOMADA da fundação continua aceito. Os inventários do
fluxo B ficam em test_auditoria_1_7_6_inventarios.py, com o apoio daqui.

Pastas descartáveis com estrutura fictícia. Ligação de pasta: junção no Windows (`mklink /J`, sem administrador),
link simbólico nos demais. Link simbólico de arquivo e FIFO entram onde o sistema permite; no Windows sem
privilégio, a folha ligada é coberta pela junção e o arquivo que não é comum é o dispositivo `NUL` — sem teste pulado.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import SCRIPTS, SKILL, criar_ligacao_dir, rodar_script
from test_retomada import OBRIGATORIOS, preencher

MODELO_MATRIZ = SKILL / "assets" / "templates" / "MATRIZ-REQUISITOS.csv"
SEGREDO = "CONTEUDO-DE-FORA-FICTICIO-1-7-6"
EFEITOS = "Ações já realizadas que não devem ser repetidas:"


def carregar(nome: str):
    spec = importlib.util.spec_from_file_location(f"_auditoria_176_{nome}", SCRIPTS / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def sha_de(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def link_de_arquivo(link: Path, alvo: Path) -> bool:
    """Link simbólico de arquivo, quando o sistema deixa (no Windows exige privilégio); sem ele, a junção cobre o caso."""
    try:
        link.symlink_to(alvo)
        return True
    except (OSError, NotImplementedError):
        return False


def nao_comum(pasta: Path) -> Path:
    """Caminho que existe e não é arquivo comum: FIFO onde houver; no Windows, o dispositivo NUL (nome reservado)."""
    pasta.mkdir(parents=True, exist_ok=True)
    if hasattr(os, "mkfifo"):
        os.mkfifo(pasta / "fila")
        return pasta / "fila"
    return pasta / "NUL"


def grande(p: Path, tamanho: int, cabeca: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("wb") as fh:
        fh.write(cabeca.encode("utf-8"))
        fh.truncate(tamanho)
    return p


class Contador:
    """`os.scandir` que conta as entradas entregues (prova de que o teto vale durante a varredura)."""

    total = 0

    def __init__(self, caminho="."):
        self.it = Contador.real(caminho)

    def __enter__(self):
        self.it.__enter__()
        return self

    def __exit__(self, *exc):
        return self.it.__exit__(*exc)

    def __iter__(self):
        return self

    def __next__(self):
        entrada = next(self.it)
        Contador.total += 1
        return entrada

    def close(self):
        self.it.close()


Contador.real = os.scandir


class _Pastas(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="auditoria-176-7-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)  # não atravessa junção (3.8+)
        self.raiz = self.base / "fundacao"
        self.raiz.mkdir()
        self.fora = self.base / "fora"
        self.fora.mkdir()
        (self.fora / "segredo.md").write_text(f"kit 1.4.1 {SEGREDO}\n", encoding="utf-8")

    def escrever(self, rel: str, texto: str) -> Path:
        p = self.raiz / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(texto, encoding="utf-8")
        return p


class TestMatrizEvidencia(_Pastas):
    """matriz.py validar: a evidência é relativa à base, sem `..`, sem ligação, arquivo comum ou pasta, com tetos."""

    def matriz(self, linhas: dict[str, dict], onde: Path | None = None) -> Path:
        onde = onde or self.raiz / "registry" / "requisitos.csv"
        onde.parent.mkdir(parents=True, exist_ok=True)
        with MODELO_MATRIZ.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        nomes = list(rows[0].keys()) + ["sha256_evidencia"]
        for r in rows:
            r.update(linhas.get(r["id"], {}))
        with onde.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=nomes, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        return onde

    @staticmethod
    def ativo(caminho: str, versao: str = "kit 1.4.1", **extra) -> dict:
        return {"estado": "implementado_ativo", "nivel_evidencia": "executado", "simulado": "nao",
                "versao_avaliada": versao, "caminho_evidencia": caminho, **extra}

    def validar(self, mat: Path, timeout: int = 120) -> tuple[int, dict, str]:
        p = rodar_script("matriz.py", "validar", "--matriz", mat, timeout=timeout)
        try:
            dados = json.loads(p.stdout)
        except ValueError:
            self.fail("saída não é JSON: " + p.stdout[-400:] + p.stderr[-400:])
        return p.returncode, dados, p.stdout

    @staticmethod
    def problemas(dados: dict) -> dict[str, str]:
        return {p.split(":", 1)[0]: p for p in dados["evidencias"]["problemas"]}

    def test_controle_formato_real_da_matriz_continua_aceito(self):
        self.escrever("evidence/kit/EVIDENCIAS-A5.md", "Ensaio do kit 1.4.1 (fictício).\n")
        r13 = self.escrever("evidence/provedores/EVIDENCIAS-R13-R14.md", "Claude Code 2.1.302: rota (fictício).\n")
        self.escrever("projects/juridico-lab/evidence/EVIDENCIAS-R60.md", "Python 3.12.10 (fictício).\n")
        self.escrever("evidence/orquestracao/2026-10/EVIDENCIAS-R05.md", "dbos 3.3.0 (fictício).\n")
        mat = self.matriz({
            "R01": self.ativo("evidence/kit/EVIDENCIAS-A5.md"),
            "R05": self.ativo("evidence/orquestracao", "dbos 3.3.0"),
            "R13": self.ativo("evidence/provedores/EVIDENCIAS-R13-R14.md", "Claude Code 2.1.302",
                              sha256_evidencia=sha_de(r13)),
            "R60": self.ativo("projects/juridico-lab/evidence/EVIDENCIAS-R60.md", "Python 3.12.10"),
        })
        codigo, dados, _ = self.validar(mat)
        self.assertEqual(codigo, 0, dados["erros"])
        self.assertEqual(dados["evidencias"]["conferidas"], ["R01", "R05", "R13", "R60"])

    def test_caminho_absoluto_ou_com_ponto_ponto_e_recusado_sem_ler_o_alvo(self):
        existe, nao_existe = (self.fora / "segredo.md").as_posix(), (self.fora / "nao-existe.md").as_posix()
        mat = self.matriz({"R12": self.ativo(existe), "R13": self.ativo("../fora/segredo.md"),
                           "R14": self.ativo(nao_existe),
                           "R15": self.ativo("evidence/../../fora/segredo.md")})
        codigo, dados, _ = self.validar(mat)
        self.assertEqual(codigo, 1)
        self.assertEqual(dados["evidencias"]["conferidas"], [], "evidência fora da base foi lida e aceita")
        probs = self.problemas(dados)
        for rid in ("R12", "R13", "R14", "R15"):
            self.assertIn("recusado", probs.get(rid, ""), probs)
        # Sem metadado do alvo: existir ou não fora da base dá a mesma resposta.
        self.assertEqual(probs["R12"].replace("R12", "R").replace(existe, "C"),
                         probs["R14"].replace("R14", "R").replace(nao_existe, "C"))

    def test_outro_projeto_fica_fora_da_base_do_projeto(self):
        (self.raiz / "projects" / "b" / "evidence").mkdir(parents=True)
        (self.raiz / "projects" / "b" / "evidence" / "caso.md").write_text(f"kit 1.4.1 {SEGREDO}\n", encoding="utf-8")
        (self.raiz / "projects" / "a" / "evidence").mkdir(parents=True)
        tipo = criar_ligacao_dir(self.raiz / "projects" / "a" / "evidence" / "elo", self.raiz / "projects" / "b" / "evidence")
        mat = self.matriz({"R12": self.ativo("../b/evidence/caso.md"), "R13": self.ativo("evidence/elo/caso.md")},
                          onde=self.raiz / "projects" / "a" / "registry" / "requisitos.csv")
        codigo, dados, _ = self.validar(mat)
        self.assertEqual(codigo, 1)
        self.assertEqual(dados["evidencias"]["conferidas"], [], f"{tipo}: a matriz do projeto leu o outro projeto")
        probs = self.problemas(dados)
        self.assertIn("recusado", probs.get("R12", ""), probs)
        self.assertIn("ligação", probs.get("R13", ""), probs)

    def test_ligacao_no_caminho_na_folha_ou_dentro_da_pasta_nao_e_seguida(self):
        (self.raiz / "evidence" / "pasta").mkdir(parents=True)
        tipo = criar_ligacao_dir(self.raiz / "evidence" / "elo", self.fora)
        (self.raiz / "evidence" / "pasta" / "leia-me.md").write_text("sem versão\n", encoding="utf-8")
        criar_ligacao_dir(self.raiz / "evidence" / "pasta" / "dentro", self.fora)
        linhas = {"R12": self.ativo("evidence/elo/segredo.md"), "R13": self.ativo("evidence/elo"),
                  "R14": self.ativo("evidence/pasta")}
        if link_de_arquivo(self.raiz / "evidence" / "R15.md", self.fora / "segredo.md"):
            linhas["R15"] = self.ativo("evidence/R15.md")
        codigo, dados, saida = self.validar(self.matriz(linhas))
        self.assertEqual(codigo, 1)
        self.assertEqual(dados["evidencias"]["conferidas"], [], f"{tipo}: a validação seguiu a ligação")
        probs = self.problemas(dados)
        for rid in ("R12", "R13", "R15"):
            if rid in linhas:
                self.assertIn("ligação", probs.get(rid, ""), probs)
        self.assertIn("cita a versão", probs.get("R14", ""), probs)  # a junção dentro da pasta não conta
        self.assertNotIn(SEGREDO, saida)

    def test_arquivo_que_nao_e_comum_nao_e_lido(self):
        alvo = nao_comum(self.raiz / "evidence")
        codigo, dados, _ = self.validar(self.matriz({"R12": self.ativo(f"evidence/{alvo.name}")}), timeout=60)
        self.assertEqual(codigo, 1)
        self.assertIn("não é arquivo comum", self.problemas(dados).get("R12", ""), dados["evidencias"])

    def test_arquivo_grande_tem_teto_e_nao_e_aceito(self):
        teto = getattr(carregar("matriz"), "TETO_EVIDENCIA", 50_000_000)
        ev = grande(self.raiz / "evidence" / "grande.log", teto + 1, "kit 1.4.1\n")
        codigo, dados, _ = self.validar(self.matriz({"R12": self.ativo("evidence/grande.log",
                                                                        sha256_evidencia=sha_de(ev))}))
        self.assertEqual(codigo, 1, "evidência acima do teto foi lida inteira e aceita")
        self.assertIn("teto", self.problemas(dados).get("R12", ""), dados["evidencias"])

    def test_pasta_de_evidencia_tem_teto_de_profundidade(self):
        fundo = self.raiz / "evidence" / "fundo"
        for _ in range(24):  # nomes curtos: o caminho fica abaixo de 260 caracteres no Windows
            fundo = fundo / "d"
        fundo.mkdir(parents=True)
        (fundo / "EVIDENCIA.md").write_text("kit 1.4.1 (fictício)\n", encoding="utf-8")
        codigo, dados, _ = self.validar(self.matriz({"R12": self.ativo("evidence/fundo")}))
        self.assertEqual(codigo, 1, "a varredura da pasta desceu sem teto de profundidade")
        self.assertIn("teto", self.problemas(dados).get("R12", ""), dados["evidencias"])

    def test_pasta_de_evidencia_para_no_teto_durante_a_varredura(self):
        mod = carregar("matriz")
        pasta = self.raiz / "evidence" / "muitos"
        pasta.mkdir(parents=True)
        for i in range(1200):
            (pasta / f"a{i:04d}.md").write_text("sem versão\n", encoding="utf-8")
        rows = [{"id": "R12", **self.ativo("evidence/muitos")}]
        Contador.total = 0
        with mock.patch("os.scandir", Contador), mock.patch.object(mod, "TETO_PASTA_ITENS", 100, create=True):
            res = mod.verify_evidence(rows, self.raiz.resolve())
        self.assertLessEqual(Contador.total, 110, "a pasta foi percorrida inteira antes do teto")
        self.assertTrue(any("teto" in p for p in res["problemas"]), res["problemas"])


class TestRetomadaHistorico(_Pastas):
    """retomada.py validar/arquivar: o histórico é relativo à pasta da RETOMADA, sem `..`, sem ligação, com teto."""

    ITENS = ["- Backup pos-b4-001 no D: verificado", "- Liberação da 1.7.6: GitHub, perfil e fundação"]

    def texto_retomada(self, ponteiros: list[str], itens: list[str]) -> str:
        valores = {**OBRIGATORIOS, EFEITOS: ""}
        texto = preencher(valores).replace(EFEITOS + " \n", EFEITOS + "\n" + "\n".join(itens) + "\n")
        linhas = texto.splitlines()
        pos = next(i for i, linha in enumerate(linhas) if linha.startswith("project_id:"))  # onde o arquivar põe
        return "\n".join(linhas[:pos] + ponteiros + linhas[pos:]) + "\n"

    def historico(self, p: Path, itens: list[str]) -> str:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.texto_retomada([], itens), encoding="utf-8", newline="\n")
        return sha_de(p)

    def validar(self, ponteiros: list[str], itens: list[str] | None = None) -> tuple[int, dict, str]:
        arq = self.raiz / "RETOMADA.md"
        arq.write_text(self.texto_retomada(ponteiros, self.ITENS if itens is None else itens), encoding="utf-8")
        p = rodar_script("retomada.py", "validar", "--arquivo", arq, timeout=60)
        try:
            return p.returncode, json.loads(p.stdout), p.stdout
        except ValueError:
            self.fail("saída não é JSON: " + p.stdout[-400:] + p.stderr[-400:])

    def de_fora(self) -> tuple[Path, str]:
        hist = self.fora / "hist.md"
        return hist, self.historico(hist, [f"- Item de fora {SEGREDO}: não deveria aparecer"])

    def test_controle_formato_real_da_retomada_continua_conferido(self):
        nomes = ("RETOMADA-20261021T100757Z.md", "RETOMADA-20261021T145609Z.md")
        ponteiros = [f"Histórico arquivado: evidence/retomada/{n} "
                     f"(sha256 {self.historico(self.raiz / 'evidence' / 'retomada' / n, self.ITENS[:i + 1])})"
                     for i, n in enumerate(nomes)]
        codigo, res, _ = self.validar(ponteiros)
        self.assertEqual(codigo, 0, res)
        self.assertEqual([h["estado"] for h in res["historicos"]], ["conferido", "conferido"])

    def test_ponteiro_absoluto_ou_com_ponto_ponto_e_recusado_sem_ler(self):
        hist, h = self.de_fora()
        ponteiros = [f"Histórico arquivado: ../fora/hist.md (sha256 {h})",
                     f"Histórico arquivado: evidence/../../fora/hist.md (sha256 {h})"]
        absolutos = " " not in str(self.base)  # o ponteiro não aceita espaço no caminho
        if absolutos:
            ponteiros += [f"Histórico arquivado: {hist.as_posix()} (sha256 {h})",
                          f"Histórico arquivado: {(self.fora / 'nao-existe.md').as_posix()} (sha256 {h})"]
        codigo, res, saida = self.validar(ponteiros)
        self.assertEqual(codigo, 1, res)
        self.assertNotIn(SEGREDO, saida, "o validar leu o arquivo de fora e mostrou o conteúdo dele")
        estados = [x["estado"] for x in res["historicos"]]
        self.assertEqual(len(estados), len(ponteiros))
        self.assertNotIn("conferido", estados)
        self.assertEqual(len(set(estados)), 1, f"existir ou não fora da pasta mudou a resposta: {estados}")
        self.assertIn("fora", estados[0])

    def test_ponteiro_por_ligacao_e_recusado(self):
        hist, h = self.de_fora()
        (self.raiz / "evidence" / "retomada").mkdir(parents=True)
        tipo = criar_ligacao_dir(self.raiz / "evidence" / "elo", self.fora)
        ponteiros = [f"Histórico arquivado: evidence/elo/hist.md (sha256 {h})"]
        if link_de_arquivo(self.raiz / "evidence" / "retomada" / "ligado.md", hist):
            ponteiros.append(f"Histórico arquivado: evidence/retomada/ligado.md (sha256 {h})")
        codigo, res, saida = self.validar(ponteiros)
        self.assertEqual(codigo, 1, res)
        self.assertNotIn(SEGREDO, saida, f"{tipo}: o validar seguiu a ligação")
        for x in res["historicos"]:
            self.assertIn("ligação", x["estado"], res["historicos"])

    def test_historico_grande_tem_teto(self):
        teto = getattr(carregar("retomada"), "TETO_HISTORICO", 5_000_000)
        p = self.raiz / "evidence" / "retomada" / "RETOMADA-grande.md"
        texto = self.texto_retomada([], self.ITENS)
        grande(p, teto + 1, texto + "\n")
        codigo, res, _ = self.validar([f"Histórico arquivado: evidence/retomada/{p.name} (sha256 {sha_de(p)})"])
        self.assertEqual(codigo, 1, "histórico acima do teto foi lido inteiro e conferido")
        self.assertIn("teto", res["historicos"][0]["estado"])

    def test_arquivar_recusa_pasta_de_historico_fora_ou_por_ligacao(self):
        arq = self.raiz / "RETOMADA.md"
        arq.write_text(self.texto_retomada([], self.ITENS), encoding="utf-8")
        antes = sha_de(arq)
        (self.raiz / "evidence").mkdir()
        criar_ligacao_dir(self.raiz / "evidence" / "elo", self.fora)
        for pasta in (self.fora / "historico", self.raiz / "evidence" / "elo" / "historico"):
            with self.subTest(pasta=pasta.relative_to(self.base).as_posix()):
                p = rodar_script("retomada.py", "arquivar", "--arquivo", arq, "--historico", pasta, timeout=60)
                self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
                self.assertFalse(json.loads(p.stdout)["ok"])
                self.assertEqual(sha_de(arq), antes, "a RETOMADA foi alterada")
                self.assertEqual(sorted(x.name for x in self.fora.iterdir()), ["segredo.md"], "escreveu fora da pasta")
        p = rodar_script("retomada.py", "arquivar", "--arquivo", arq, "--historico", self.raiz / "evidence" / "retomada",
                         "--nome", "../../../fora/nome.md", timeout=60)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertEqual(sorted(x.name for x in self.fora.iterdir()), ["segredo.md"], "o --nome saiu da pasta")


if __name__ == "__main__":
    unittest.main()
