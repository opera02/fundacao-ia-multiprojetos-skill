"""Auditoria de segurança da 1.7.6 (Codex Security, 21/10/2026), achado #6 — o pacote instalável preso à fonte revisada.

Na 1.7.6 a CI rodava os testes da fonte e nunca comparava o `.skill` e o `.zip` versionados em entrega/dist com a
árvore da skill; o empacotar.py rodava a ferramenta externa (skill-creator) que quem chamava indicasse e só conferia a
estrutura do zip. Um pacote com um membro a mais, a menos ou mudado, com o SHA256SUMS.txt do mesmo commit ajustado,
passava. Agora:
- `entrega/verificar_pacote.py` confere dist/ (SHA256SUMS.txt, EMPACOTAMENTO.json, estrutura de cada zip, .skill ×
  completo, anteriores/) e, com --exigir-igual-a-arvore (o modo da CI pública), exige que cada pacote seja
  exatamente a árvore: a mesma versão, os mesmos membros, os mesmos bytes;
- o empacotar.py recusa ferramenta com hash diferente do registrado (FERRAMENTA_ESPERADA), roda uma cópia só com os
  bytes conferidos e confere cada pacote gerado contra a árvore antes de gravar o SHA256SUMS.txt.

Os pacotes adulterados são cópias dos pacotes REAIS de entrega/dist, comparadas com a árvore extraída do próprio
completo, numa pasta temporária: o teste não depende de a árvore de desenvolvimento estar na versão do pacote (no
preparo de uma versão ela não está). O dublê do skill-creator é fictício; nada é empacotado de verdade e a entrega
real não é tocada. Falham antes da 1.7.7 (o verificador não existia; o empacotador rodava qualquer ferramenta, da
pasta dela, e não comparava o pacote com a árvore) e passam depois.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest import mock

from test_auditoria_1_5_0_instalacao import ligar_pasta
from test_empacotar import carregar_modulo as carregar_empacotador

ENTREGA = Path(__file__).resolve().parents[1]
DIST_REAL = ENTREGA / "dist"
SKILL_REAL = ENTREGA.parent / "fundacao-ia-multiprojetos"
NOME = "fundacao-ia-multiprojetos"
PACOTE, COMPLETO = f"{NOME}.skill", f"{NOME}-completo.zip"
ARQUIVO_COMUM = (stat.S_IFREG | 0o666) << 16  # o modo que o zipfile grava no Windows


def carregar_verificador():
    spec = importlib.util.spec_from_file_location("verificar_pacote_em_teste", ENTREGA / "verificar_pacote.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # só define constantes e funções
    return mod


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def info(nome: str, modelo: zipfile.ZipInfo | None = None, atributos: int = ARQUIVO_COMUM) -> zipfile.ZipInfo:
    """Entrada nova com os atributos do modelo (ou de arquivo comum do Windows)."""
    novo = zipfile.ZipInfo(nome, date_time=modelo.date_time if modelo else (2026, 1, 1, 0, 0, 0))
    novo.compress_type = modelo.compress_type if modelo else zipfile.ZIP_DEFLATED
    novo.external_attr = modelo.external_attr if modelo else atributos
    novo.create_system = modelo.create_system if modelo else 0
    return novo


def reescrever(caminho: Path, mudar: dict | None = None, acrescentar=(), antes: bytes = b"", depois: bytes = b"",
               comentario: bytes = b"") -> None:
    """Regrava o zip: membros mudados (bytes) ou tirados (None), entradas acrescentadas no fim ((nome ou ZipInfo,
    bytes)) e bytes antes, depois ou como comentário. Os membros guardam os atributos originais."""
    mudar = mudar or {}
    with zipfile.ZipFile(caminho) as z:
        membros = [(i, z.read(i)) for i in z.infolist()]
    buf = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # nome repetido, quando houver, é de propósito
        with zipfile.ZipFile(buf, "w") as z:
            for i, dados in membros:
                if mudar.get(i.filename, dados) is not None:
                    z.writestr(info(i.filename, i), mudar.get(i.filename, dados))
            for nome, dados in acrescentar:
                z.writestr(nome if isinstance(nome, zipfile.ZipInfo) else info(nome, membros[0][0]), dados)
            z.comment = comentario
    caminho.write_bytes(antes + buf.getvalue() + depois)


class _DistReal(unittest.TestCase):
    """dist/ descartável com os pacotes reais e a árvore extraída do completo real."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="verificar-pacote-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.dist = self.base / "dist"
        self.dist.mkdir()
        for nome in (PACOTE, COMPLETO, "SHA256SUMS.txt", "EMPACOTAMENTO.json"):
            shutil.copyfile(DIST_REAL / nome, self.dist / nome)
        # Desde a revisão de segurança da 1.7.7 (R177-ATU-04), a lista dos pacotes fica ao lado de dist/ e o modo
        # rígido exige nela os pacotes de dist/: a entrega descartável a leva, como leva os pacotes.
        shutil.copyfile(ENTREGA / "HISTORICO-PACOTES-SHA256.txt", self.base / "HISTORICO-PACOTES-SHA256.txt")
        with zipfile.ZipFile(DIST_REAL / COMPLETO) as z:
            z.extractall(self.base / "arvore")
        self.skill = self.base / "arvore" / NOME
        self.vp = carregar_verificador()
        with zipfile.ZipFile(self.dist / PACOTE) as z:
            nomes = sorted(z.namelist())
        self.um_membro = next(n for n in nomes if n.startswith(f"{NOME}/references/"))

    def verificar(self, estrito: bool = True) -> dict:
        return self.vp.verificar(self.dist, self.skill, exigir_igual_a_arvore=estrito)

    def resselar(self) -> None:
        """Ajusta o SHA256SUMS.txt e o EMPACOTAMENTO.json aos pacotes, como faria quem adulterou o pacote no commit."""
        hashes = {n: sha(self.dist / n) for n in (PACOTE, COMPLETO)}
        (self.dist / "SHA256SUMS.txt").write_bytes("".join(f"{h}  {n}\n" for n, h in hashes.items()).encode())
        emp = json.loads((self.dist / "EMPACOTAMENTO.json").read_text(encoding="utf-8"))
        emp["sha256"] = hashes
        contagem = {}
        for n in hashes:
            with zipfile.ZipFile(self.dist / n) as z:
                contagem[n] = len(z.namelist())
        emp["arquivos"] = contagem
        (self.dist / "EMPACOTAMENTO.json").write_bytes((json.dumps(emp, ensure_ascii=False, indent=2) + "\n").encode())

    def reprova(self, res: dict, *trechos: str) -> None:
        self.assertFalse(res["ok"], f"o pacote adulterado foi aprovado: {res['problemas'][:5]}")
        texto = " | ".join(res["problemas"])
        for trecho in trechos:
            self.assertIn(trecho, texto)


class TestN6VerificadorDoPacote(_DistReal):
    def test_n6_estado_atual_coerente_e_aprovado(self):
        res = self.verificar()
        self.assertTrue(res["ok"], res["problemas"][:10])
        self.assertTrue(res["fonte"]["igual_ao_pacote"], res["fonte"])
        emp = json.loads((self.dist / "EMPACOTAMENTO.json").read_text(encoding="utf-8"))
        self.assertEqual({n: d["arquivos"] for n, d in res["pacotes"].items()}, emp["arquivos"])

    def test_n6_membro_acrescentado_sem_mudar_a_fonte_reprova(self):
        reescrever(self.dist / PACOTE, acrescentar=[(f"{NOME}/scripts/extra.py", b"print('fora da fonte')\n")])
        self.resselar()
        self.reprova(self.verificar(), f"{NOME}/scripts/extra.py a mais")
        self.reprova(self.verificar(estrito=False), f"{NOME}/scripts/extra.py a mais")  # o completo não o tem

    def test_n6_membro_removido_sem_mudar_a_fonte_reprova(self):
        reescrever(self.dist / PACOTE, mudar={self.um_membro: None})
        self.resselar()
        self.reprova(self.verificar(), f"{self.um_membro} a menos")

    def test_n6_membro_mudado_sem_mudar_a_fonte_reprova(self):
        reescrever(self.dist / PACOTE, mudar={self.um_membro: b"conteudo trocado\n"})
        self.resselar()
        self.reprova(self.verificar(), f"{self.um_membro} com bytes diferentes")

    def test_n6_mudanca_igual_nos_dois_pacotes_so_a_comparacao_com_a_arvore_pega(self):
        """Por que a CI pública usa --exigir-igual-a-arvore: os dois pacotes mudados juntos, com os hashes do commit
        ajustados, são coerentes entre si; só a comparação com a fonte revisada mostra a diferença."""
        for nome in (PACOTE, COMPLETO):
            reescrever(self.dist / nome, mudar={self.um_membro: b"instrucao escondida\n"})
        self.resselar()
        self.assertTrue(self.verificar(estrito=False)["ok"], "o modo de desenvolvimento reprovou dist/ coerente")
        self.reprova(self.verificar(), f"{self.um_membro} com bytes diferentes da árvore")

    def test_n6_sha256sums_que_nao_confere_reprova(self):
        reescrever(self.dist / PACOTE, mudar={self.um_membro: b"conteudo trocado\n"})
        self.reprova(self.verificar(estrito=False), "não confere com o SHA256SUMS.txt")

    def test_n6_bytes_fora_das_entradas_reprovam(self):
        original = (self.dist / PACOTE).read_bytes()
        casos = {"antes": {"antes": b"MZ" + b"\0" * 62}, "depois": {"depois": b"<html>carga</html>"},
                 "comentario": {"comentario": b"carga no comentario"}}
        for rotulo, extra in casos.items():
            with self.subTest(rotulo):
                (self.dist / PACOTE).write_bytes(original)
                reescrever(self.dist / PACOTE, **extra)
                self.resselar()
                self.reprova(self.verificar(estrito=False), "fora")

    def test_n6_entrada_que_nao_e_arquivo_comum_reprova(self):
        original = (self.dist / PACOTE).read_bytes()
        link = info(f"{NOME}/references/atalho.md", atributos=(stat.S_IFLNK | 0o777) << 16)
        link.create_system = 3
        setuid = info(f"{NOME}/scripts/setuid.py", atributos=(stat.S_IFREG | 0o4755) << 16)
        setuid.create_system = 3
        casos = {"link simbólico": [(link, b"../../../segredo")], "modo especial": [(setuid, b"x")],
                 "pasta": [(info(f"{NOME}/references/vazia/", atributos=(stat.S_IFDIR | 0o755) << 16 | 0x10), b"")],
                 "nome repetido": [(self.um_membro, b"segunda entrada")],
                 "outra caixa": [(self.um_membro.upper().replace(NOME.upper(), NOME), b"outra caixa")],
                 "fora da pasta": [("outra-pasta/x.md", b"x")], "componente ..": [(f"{NOME}/../x.md", b"x")]}
        for rotulo, extra in casos.items():
            with self.subTest(rotulo):
                (self.dist / PACOTE).write_bytes(original)
                reescrever(self.dist / PACOTE, acrescentar=extra)
                self.resselar()
                self.reprova(self.verificar(estrito=False))

    def test_n6_versao_da_arvore_diferente_do_pacote(self):
        """Intervalo de preparo: a árvore já está na versão seguinte e o pacote ainda é o da anterior. O modo de
        desenvolvimento aprova e relata; o da CI pública reprova."""
        skill_md = self.skill / "SKILL.md"
        skill_md.write_bytes(re.sub(rb'(version:\s*"?)[^"\s]+', rb"\g<1>9.9.9", skill_md.read_bytes(), count=1))
        res = self.verificar(estrito=False)
        self.assertTrue(res["ok"], res["problemas"][:5])
        self.assertEqual(res["fonte"]["versao"], "9.9.9")
        self.assertFalse(res["fonte"]["igual_ao_pacote"])
        self.reprova(self.verificar(), "versão '9.9.9'")

    def test_n6_ligacao_na_arvore_impede_a_comparacao(self):
        fora = self.base / "fora"
        fora.mkdir()
        (fora / "credencial.txt").write_text("CREDENCIAL-FICTICIA", encoding="utf-8")
        ligar_pasta(self.skill / "references" / "anexo", fora, self)  # junção no Windows, link simbólico nos demais
        self.reprova(self.verificar(), "ligação")

    def test_n6_conjunto_anterior_adulterado_reprova(self):
        versao = json.loads((self.dist / "EMPACOTAMENTO.json").read_text(encoding="utf-8"))["versao"]
        guardado = self.dist / "anteriores" / versao
        guardado.mkdir(parents=True)
        shutil.copyfile(self.dist / PACOTE, guardado / PACOTE)
        (guardado / "SHA256SUMS.txt").write_bytes(f"{sha(guardado / PACOTE)}  {PACOTE}\n".encode())
        self.assertTrue(self.verificar()["ok"], "o conjunto guardado coerente foi reprovado")
        with open(guardado / PACOTE, "ab") as f:
            f.write(b"x")
        self.reprova(self.verificar(), "SHA-256 não confere com o SHA256SUMS.txt da pasta")
        shutil.copyfile(self.dist / PACOTE, guardado / PACOTE)
        guardado.rename(self.dist / "anteriores" / "0.0.1")
        self.reprova(self.verificar(), "não é a da pasta")

    def test_n6_dist_real_confere_no_modo_de_desenvolvimento(self):
        """dist/ versionado é coerente (hashes, metadados, estrutura, .skill × completo, anteriores) em qualquer ponto
        do preparo; a igualdade com a árvore fica com a CI pública e a liberação."""
        res = self.vp.verificar(DIST_REAL, SKILL_REAL)
        self.assertTrue(res["ok"], res["problemas"][:10])


class TestN6Empacotador(unittest.TestCase):
    """empacotar.py com dist e skill-creator descartáveis (dublê); o subprocesso do package_skill é simulado."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="empacotar-1-7-7-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.dist = self.base / "dist"
        self.dist.mkdir()
        (self.dist / PACOTE).write_bytes(b"PACOTE-ANTERIOR-FICTICIO")
        (self.dist / COMPLETO).write_bytes(b"COMPLETO-ANTERIOR-FICTICIO")
        (self.dist / "SHA256SUMS.txt").write_bytes(b"HASHES-ANTERIORES-FICTICIOS\n")
        self.antes = {p.name: p.read_bytes() for p in self.dist.iterdir()}
        self.skill = self.base / "fonte" / NOME
        (self.skill / "evals").mkdir(parents=True)
        (self.skill / "references").mkdir()
        (self.skill / "SKILL.md").write_bytes(f'---\nname: {NOME}\nmetadata:\n  version: "9.9.9"\n---\n'.encode())
        (self.skill / "references" / "nota.md").write_bytes(b"nota ficticia\n")
        (self.skill / "evals" / "evals.json").write_bytes(b"{}")
        self.creator = self.base / "skill-creator"
        (self.creator / "scripts").mkdir(parents=True)
        self.registrados = {"scripts/__init__.py": b"", "scripts/package_skill.py": b"# dubl\xc3\xaa ficticio\n",
                            "scripts/quick_validate.py": b"# dubl\xc3\xaa ficticio\n"}
        for rel, dados in self.registrados.items():
            (self.creator / rel).write_bytes(dados)
        self.mod = carregar_empacotador()
        self.mod.DIST, self.mod.SKILL = self.dist, self.skill
        self.mod.FERRAMENTA_ESPERADA = {rel: hashlib.sha256(d).hexdigest() for rel, d in self.registrados.items()}
        self.chamadas = []

    def rodar(self, gerar):
        def efeito(cmd, **kw):
            pasta = Path(kw.get("cwd", "."))
            self.chamadas.append({"cmd": cmd, "cwd": pasta, "arquivos": {
                p.relative_to(pasta).as_posix(): p.read_bytes() for p in pasta.rglob("*") if p.is_file()}})
            return gerar(cmd, **kw)
        saida = io.StringIO()
        with mock.patch.object(self.mod.subprocess, "run", side_effect=efeito), \
                mock.patch.object(sys, "argv", ["empacotar.py", "--skill-creator", str(self.creator)]), \
                contextlib.redirect_stdout(saida), contextlib.redirect_stderr(saida):
            try:
                rc = self.mod.main()
            except BaseException as exc:  # noqa: BLE001 — qualquer queda conta como falha do empacotamento
                rc = f"excecao:{type(exc).__name__}"
        self.saida = saida.getvalue()
        return rc

    @staticmethod
    def dubla_package_skill(acrescentar=(), tirar=(), mudar=None):
        """Dublê do package_skill.py: o .skill com os arquivos da árvore (cmd[-2]) que ele leva — menos evals/ na
        raiz —, com entradas acrescentadas, tiradas ou mudadas."""
        def efeito(cmd, **kw):
            skill, destino = Path(cmd[-2]), Path(cmd[-1])
            with zipfile.ZipFile(destino / PACOTE, "w", zipfile.ZIP_DEFLATED) as z:
                for p in sorted(skill.rglob("*")):
                    rel = p.relative_to(skill.parent).as_posix()
                    if not p.is_file() or rel.split("/")[1] == "evals" or rel in tirar:
                        continue
                    if mudar and rel in mudar:
                        z.writestr(info(rel), mudar[rel])
                    else:
                        z.write(p, rel)
                for nome, dados in acrescentar:
                    z.writestr(info(nome), dados)
            return subprocess.CompletedProcess(cmd, 0, "pacote fictício gerado", "")
        return efeito

    def preservada(self) -> None:
        for nome, dados in self.antes.items():
            self.assertEqual((self.dist / nome).read_bytes(), dados, f"{nome} mudou numa recusa")
        self.assertFalse((self.dist / "EMPACOTAMENTO.json").exists())
        self.assertFalse(any(p.name.startswith(".preparo-") for p in self.dist.iterdir()), "sobrou área de preparo")

    def test_n6_ferramenta_com_hash_diferente_do_registrado_e_recusada(self):
        for rel in ("scripts/package_skill.py", "scripts/quick_validate.py"):
            with self.subTest(rel):
                (self.creator / rel).write_bytes(self.registrados[rel] + b"import os  # mudanca\n")
                rc = self.rodar(self.dubla_package_skill())
                (self.creator / rel).write_bytes(self.registrados[rel])
                self.assertEqual(rc, 2, f"empacotou com a ferramenta divergente: {self.saida[-400:]}")
                self.assertEqual(self.chamadas, [], "a ferramenta divergente chegou a rodar")
                self.assertIn("FERRAMENTA_ESPERADA", self.saida)
                self.assertIn(rel, self.saida)
                self.preservada()

    def test_n6_ferramenta_roda_de_uma_copia_so_com_os_arquivos_conferidos(self):
        (self.creator / "zipfile.py").write_bytes(b"raise SystemExit('modulo plantado na pasta do skill-creator')\n")
        rc = self.rodar(self.dubla_package_skill())
        self.assertEqual(rc, 0, self.saida[-600:])
        chamada = self.chamadas[0]
        self.assertNotEqual(chamada["cwd"].resolve(), self.creator.resolve(), "rodou da pasta do skill-creator")
        self.assertEqual(chamada["arquivos"], self.registrados, "a pasta de trabalho não tem só os bytes conferidos")
        self.assertIn("-E", chamada["cmd"], "o PYTHONPATH do ambiente entraria antes da biblioteca padrão")

    def test_n6_pacote_gerado_que_nao_e_a_arvore_e_recusado_antes_do_sha256sums(self):
        casos = {"membro a mais": {"acrescentar": [(f"{NOME}/scripts/carga.py", b"print('carga')\n")]},
                 "membro a menos": {"tirar": (f"{NOME}/references/nota.md",)},
                 "membro mudado": {"mudar": {f"{NOME}/references/nota.md": b"nota trocada\n"}}}
        for rotulo, kw in casos.items():
            with self.subTest(rotulo):
                rc = self.rodar(self.dubla_package_skill(**kw))
                self.assertEqual(rc, 1, f"promoveu um pacote que não é a árvore: {self.saida[-400:]}")
                self.assertIn("não é a árvore", self.saida)
                self.preservada()

    def test_n6_pacote_igual_a_arvore_e_promovido_e_aprovado_pelo_verificador(self):
        for p in self.dist.iterdir():  # sem o conjunto anterior fictício (não é zip): aqui interessa o novo
            p.unlink()
        rc = self.rodar(self.dubla_package_skill())
        self.assertEqual(rc, 0, self.saida[-600:])
        res = carregar_verificador().verificar(self.dist, self.skill, exigir_igual_a_arvore=True)
        self.assertTrue(res["ok"], res["problemas"][:10])
        emp = json.loads((self.dist / "EMPACOTAMENTO.json").read_text(encoding="utf-8"))
        self.assertEqual(emp["ferramenta"]["arquivos_conferidos"], self.mod.FERRAMENTA_ESPERADA)


if __name__ == "__main__":
    unittest.main()
