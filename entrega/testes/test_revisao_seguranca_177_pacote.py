"""Revisão de segurança independente da 1.7.7 (simulação da liberação real), R177-ATU-04: a CI rígida cobre a
transferência e prende dist/anteriores/ à história.

Na 1.7.7 em preparo, `verificar_pacote.py --exigir-igual-a-arvore` (o passo da CI pública) só conferia dist/: o
README-ENTREGA manda enviar ao claude.ai o `transferencia/<nome>-<versão>-para-claude-ai.zip` (o da 1.7.6 é byte a byte
o .skill), o zip principal da transferência leva o .skill e o instalador, e nada disso era conferido; e
`conferir_anteriores` aceitava um conjunto novo coerente consigo mesmo (pacote trocado com o SHA256SUMS.txt da pasta
ajustado). Agora:
- `--exigir-transferencia` (a CI pública): o -para-claude-ai.zip da versão de dist/ existe e é byte a byte o .skill; o
  zip principal passa pelo `examinar_zip`, leva o .skill igual, o instalador igual ao de entrega/ e o SHA256SUMS.txt
  coerente; o .skill de toda transferência de versão anterior está na lista; outro arquivo na pasta recusa;
- `entrega/HISTORICO-PACOTES-SHA256.txt`: os pacotes liberados (`<sha256>  <versão>/<arquivo>`), gerado do que
  existia na 1.7.7; pacote de dist/anteriores/ fora dela recusa, a mesma chave com outro hash recusa, e com
  `--exigir-igual-a-arvore` os pacotes de dist/ têm de estar nela (o empacotar.py os acrescenta);
- `--lista-so-cresce` (a CI pública, com a história inteira do git): toda versão anterior da lista está na atual.
Ordem da liberação: o empacotamento (etapa 02) gera dist/ e só a etapa 03 monta a transferência; por isso a liberação
confere com `--exigir-igual-a-arvore` sem a transferência, e só a CI exige `--exigir-transferencia`. No commit do
pacote, antes da etapa 03, a transferência da versão de dist/ não existe: os testes montam a de ensaio a partir de
dist/ (segunda passada, R177B-B-04), e a etapa 01 de uma liberação retomada não para aqui.
Pastas descartáveis, com cópias dos pacotes e da transferência reais; a entrega real não é tocada.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import test_auditoria_1_7_7_pacote as base_177
from test_auditoria_1_7_7_pacote import (COMPLETO, DIST_REAL, ENTREGA, NOME, PACOTE, carregar_verificador,
                                         reescrever)

HISTORICO = "HISTORICO-PACOTES-SHA256.txt"
TRANSF_REAL = ENTREGA / "transferencia"
WORKFLOW = ENTREGA.parent / ".github" / "workflows" / "validar.yml"
MEMBROS = ("LEIA-ME.txt", PACOTE, "instalar_skill.py", "SHA256SUMS.txt")  # do zip principal, nesta ordem


def sha(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def tupla(versao: str) -> tuple:
    return tuple(int(x) for x in versao.split("."))


def leia_me_de_ensaio(origem: Path, versao: str, hash_skill: str) -> bytes:
    """O LEIA-ME da versão mais recente que tem zip principal em `origem`, com a versão e o hash do .skill dela trocados
    pelos de dist/: o modelo que o montador da etapa 03 usa. Sem nenhuma, um LEIA-ME mínimo com o instalador."""
    padrao = re.compile(re.escape(NOME) + r"-(\d+(?:\.\d+)+)\.zip")
    outras = sorted((tupla(m[1]), m[1]) for m in map(padrao.fullmatch, (p.name for p in origem.iterdir()))
                    if m and m[1] != versao)
    if not outras:
        return (f"Skill {NOME} {versao} - pacote para instalar em outro computador\n\n"
                f"   python instalar_skill.py instalar --origem {PACOTE} --sha256 {hash_skill}\n").encode("utf-8")
    anterior = outras[-1][1]
    with zipfile.ZipFile(origem / f"{NOME}-{anterior}.zip") as z:
        texto = z.read(f"{NOME}-{anterior}/LEIA-ME.txt").decode("utf-8")
        hash_anterior = sha(z.read(f"{NOME}-{anterior}/{PACOTE}"))
    texto = texto.replace(hash_anterior, hash_skill).replace(hash_anterior.upper(), hash_skill.upper())
    return re.sub(r"(?<![\d.])" + re.escape(anterior) + r"(?!\d|\.\d)", versao, texto).encode("utf-8")


def transferencia_da_versao(origem: Path, destino: Path, versao: str, skill: bytes) -> bool:
    """Põe em `destino` o zip principal e o -para-claude-ai.zip da `versao` (a de dist/) que estão em `origem`. Sem
    eles — liberação retomada entre as etapas 02 e 03, com dist/ já na versão nova (R177B-B-04) —, monta os de ensaio
    como a etapa 03: o -para-claude-ai.zip é o .skill de dist/ (`skill`), e o principal leva o LEIA-ME de ensaio, o
    .skill, o instalar_skill.py da árvore e o SHA256SUMS.txt. Devolve se a transferência é a real."""
    principal, claude = f"{NOME}-{versao}.zip", f"{NOME}-{versao}-para-claude-ai.zip"
    if (origem / principal).is_file() and (origem / claude).is_file():
        for nome in (principal, claude):
            shutil.copyfile(origem / nome, destino / nome)
        return True
    (destino / claude).write_bytes(skill)
    membros = {"LEIA-ME.txt": leia_me_de_ensaio(origem, versao, sha(skill)), PACOTE: skill,
               "instalar_skill.py": (ENTREGA / "instalar_skill.py").read_bytes()}
    membros["SHA256SUMS.txt"] = "".join(f"{sha(membros[n])}  {n}\n" for n in (PACOTE, "instalar_skill.py")).encode()
    with zipfile.ZipFile(destino / principal, "w") as z:
        for nome in MEMBROS:
            z.writestr(base_177.info(f"{NOME}-{versao}/{nome}"), membros[nome])
    return False


def remontar(caminho: Path, mudar: dict | None = None, acrescentar=(), sums_coerente: bool = True) -> None:
    """Regrava um zip principal da transferência com membros mudados (nome dentro da pasta -> bytes) ou acrescentados,
    e o SHA256SUMS.txt de dentro recalculado (como faria quem o adulterou com cuidado) ou mantido."""
    with zipfile.ZipFile(caminho) as z:
        pasta = z.namelist()[0].split("/", 1)[0]
        membros = {i.filename.split("/", 1)[1]: (i, z.read(i)) for i in z.infolist()}
    for nome, dados in (mudar or {}).items():
        membros[nome] = (membros[nome][0], dados)
    if sums_coerente:
        linhas = "".join(f"{sha(membros[n][1])}  {n}\n" for n in (PACOTE, "instalar_skill.py"))
        membros["SHA256SUMS.txt"] = (membros["SHA256SUMS.txt"][0], linhas.encode())
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nome, (info, dados) in membros.items():
            z.writestr(base_177.info(f"{pasta}/{nome}", info), dados)
        for nome, dados in acrescentar:
            z.writestr(f"{pasta}/{nome}", dados)
    caminho.write_bytes(buf.getvalue())


class _Entrega(unittest.TestCase):
    """entrega/ descartável: dist/ real, a árvore extraída do completo real, a lista real e a transferência da versão
    de dist/, com o instalador que ela leva no lugar de entrega/instalar_skill.py (a árvore em preparo já tem outro).
    Sem a transferência real da versão de dist/ (antes da etapa 03), a de ensaio (`transferencia_da_versao`). Desde a
    terceira passada (R177C-B-05), o --exigir-transferencia exige na pasta cada zip principal da lista: a entrega
    descartável leva também os das outras versões, da transferência real."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="revisao-177-pacote-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.dist = self.base / "dist"
        self.dist.mkdir()
        for nome in (PACOTE, COMPLETO, "SHA256SUMS.txt", "EMPACOTAMENTO.json"):
            shutil.copyfile(DIST_REAL / nome, self.dist / nome)
        shutil.copyfile(ENTREGA / HISTORICO, self.base / HISTORICO)
        with zipfile.ZipFile(DIST_REAL / COMPLETO) as z:
            z.extractall(self.base / "arvore")
        self.skill = self.base / "arvore" / NOME
        self.versao = json.loads((DIST_REAL / "EMPACOTAMENTO.json").read_text(encoding="utf-8"))["versao"]
        self.transf = self.base / "transferencia"
        self.transf.mkdir()
        self.principal = self.transf / f"{NOME}-{self.versao}.zip"
        self.claude = self.transf / f"{NOME}-{self.versao}-para-claude-ai.zip"
        self.real = transferencia_da_versao(TRANSF_REAL, self.transf, self.versao, (self.dist / PACOTE).read_bytes())
        for arq in TRANSF_REAL.iterdir():  # os zips principais publicados das outras versões (R177C-B-05)
            m = re.fullmatch(re.escape(NOME) + r"-(\d+(?:\.\d+)+)\.zip", arq.name)
            if m and m[1] != self.versao:
                shutil.copyfile(arq, self.transf / arq.name)
        if not self.real:  # antes da etapa 03, a lista também não tem a linha do zip principal da versão (R177B-B-07)
            lista, chave = self.base / HISTORICO, f"  {self.versao}/{self.principal.name}"
            linhas = lista.read_text(encoding="utf-8").splitlines()
            lista.write_text("".join(x + "\n" for x in linhas if not x.endswith(chave)), encoding="utf-8", newline="\n")
        with zipfile.ZipFile(self.principal) as z:
            (self.base / "instalar_skill.py").write_bytes(z.read(f"{NOME}-{self.versao}/instalar_skill.py"))
        self.vp = carregar_verificador()

    def verificar(self, **opcoes) -> dict:
        opcoes.setdefault("exigir_igual_a_arvore", True)
        opcoes.setdefault("exigir_transferencia", True)
        return self.vp.verificar(self.dist, self.skill, **opcoes)

    def reprova(self, res: dict, *trechos: str) -> None:
        self.assertFalse(res["ok"], "a entrega adulterada foi aprovada")
        texto = " | ".join(res["problemas"])
        for trecho in trechos:
            self.assertIn(trecho, texto)


class TestTransferenciaNaCIRigida(_Entrega):
    def test_transferencia_da_versao_de_dist_confere(self):
        res = self.verificar()
        self.assertTrue(res["ok"], res["problemas"][:10])
        self.assertEqual(res["transferencia"]["versao"], self.versao)

    def test_transferencia_real_inteira_confere_com_a_lista(self):
        da_versao = {p.name: p.read_bytes() for p in (self.principal, self.claude)}
        shutil.rmtree(self.transf)
        shutil.copytree(TRANSF_REAL, self.transf)
        for nome, dados in da_versao.items():  # a de ensaio, se a real da versão de dist/ ainda não existe (R177B-B-04)
            if not (self.transf / nome).exists():
                (self.transf / nome).write_bytes(dados)
        res = self.verificar()
        self.assertTrue(res["ok"], res["problemas"][:10])

    def test_para_claude_ai_diferente_do_skill_reprova(self):
        with open(self.claude, "ab") as f:
            f.write(b"carga")
        self.reprova(self.verificar(), "para-claude-ai.zip")

    def test_para_claude_ai_ausente_reprova(self):
        self.claude.unlink()
        self.reprova(self.verificar(), f"{self.claude.name} ausente")

    def test_zip_principal_com_outro_skill_reprova(self):
        remontar(self.principal, mudar={PACOTE: (DIST_REAL / COMPLETO).read_bytes()})
        self.reprova(self.verificar(), PACOTE)

    def test_zip_principal_com_instalador_adulterado_reprova(self):
        instalador = (self.base / "instalar_skill.py").read_bytes() + b"\nprint('carga')\n"
        remontar(self.principal, mudar={"instalar_skill.py": instalador})
        self.reprova(self.verificar(), "instalar_skill.py")

    def test_zip_principal_com_sums_incoerente_ou_membro_a_mais_reprova(self):
        original = self.principal.read_bytes()
        casos = {"sums": {"mudar": {"SHA256SUMS.txt": b"0" * 64 + b"  " + PACOTE.encode() + b"\n"},
                          "sums_coerente": False},
                 "membro a mais": {"acrescentar": [("instalar.bat", b"echo carga\r\n")]}}
        for rotulo, kw in casos.items():
            with self.subTest(rotulo):
                self.principal.write_bytes(original)
                remontar(self.principal, **kw)
                self.reprova(self.verificar())

    def test_arquivo_estranho_ou_skill_antigo_fora_da_lista_reprova(self):
        (self.transf / "instalar.bat").write_bytes(b"echo carga\r\n")
        self.reprova(self.verificar(), "instalar.bat")
        (self.transf / "instalar.bat").unlink()
        (self.transf / f"{NOME}-1.0.0-para-claude-ai.zip").write_bytes((DIST_REAL / PACOTE).read_bytes() + b"x")
        self.reprova(self.verificar(), "1.0.0")

    def test_liberacao_confere_dist_antes_de_a_transferencia_existir(self):
        shutil.rmtree(self.transf)
        res = self.verificar(exigir_transferencia=False)
        self.assertTrue(res["ok"], res["problemas"][:10])
        self.reprova(self.verificar(), "transferencia")

    def test_linha_de_comando_da_ci(self):
        cmd = [sys.executable, "-B", str(ENTREGA / "verificar_pacote.py"), "--dist", str(self.dist), "--skill",
               str(self.skill), "--exigir-igual-a-arvore", "--exigir-transferencia"]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, r.stdout[-800:])
        with open(self.claude, "ab") as f:
            f.write(b"carga")
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 1, r.stdout[-800:])


class TestAnterioresPresosALista(_Entrega):
    def adulterado(self) -> bytes:
        """Cópia do .skill de dist/ com um membro trocado: coerente consigo mesma, outro hash."""
        copia = self.base / "adulterado.skill"
        shutil.copyfile(DIST_REAL / PACOTE, copia)
        with zipfile.ZipFile(copia) as z:
            membro = next(n for n in sorted(z.namelist()) if n.startswith(f"{NOME}/references/"))
        reescrever(copia, mudar={membro: b"instrucao escondida\n"})
        return copia.read_bytes()

    def test_conjunto_anterior_novo_e_coerente_fora_da_lista_reprova(self):
        conjunto = self.dist / "anteriores" / f"{self.versao}-20991231T000000Z"
        conjunto.mkdir(parents=True)
        dados = self.adulterado()
        (conjunto / PACOTE).write_bytes(dados)
        (conjunto / "SHA256SUMS.txt").write_text(f"{sha(dados)}  {PACOTE}\n", encoding="utf-8")
        self.reprova(self.vp.verificar(self.dist, self.skill), HISTORICO)          # também no modo de desenvolvimento

    def test_conjunto_anterior_trocado_com_sums_ajustado_reprova(self):
        conjunto = self.dist / "anteriores" / self.versao
        conjunto.mkdir(parents=True)
        shutil.copyfile(DIST_REAL / PACOTE, conjunto / PACOTE)
        (conjunto / "SHA256SUMS.txt").write_text(f"{sha((DIST_REAL / PACOTE).read_bytes())}  {PACOTE}\n",
                                                 encoding="utf-8")
        self.assertTrue(self.verificar()["ok"])                                      # o pacote liberado, guardado
        dados = self.adulterado()
        (conjunto / PACOTE).write_bytes(dados)
        (conjunto / "SHA256SUMS.txt").write_text(f"{sha(dados)}  {PACOTE}\n", encoding="utf-8")
        self.reprova(self.verificar(), HISTORICO)

    def test_lista_com_a_mesma_chave_e_outro_hash_reprova(self):
        lista = self.base / HISTORICO
        with open(lista, "a", encoding="utf-8", newline="\n") as f:
            f.write(f"{'0' * 64}  {self.versao}/{PACOTE}\n")
        self.reprova(self.verificar(), "repetid")

    def test_pacote_de_dist_fora_da_lista_reprova_no_modo_rigido(self):
        lista = self.base / HISTORICO
        linhas = [linha for linha in lista.read_text(encoding="utf-8").splitlines()
                  if not linha.endswith(f"  {self.versao}/{PACOTE}")]
        lista.write_text("\n".join(linhas) + "\n", encoding="utf-8", newline="\n")
        self.assertTrue(self.vp.verificar(self.dist, self.skill)["ok"])             # desenvolvimento: só relata
        self.reprova(self.verificar(exigir_transferencia=False), HISTORICO)

    def test_lista_real_cobre_os_pacotes_reais(self):
        res = self.vp.verificar(DIST_REAL, ENTREGA.parent / NOME)
        self.assertTrue(res["ok"], res["problemas"][:10])
        historico, problemas = self.vp.ler_historico(ENTREGA / HISTORICO)
        self.assertEqual(problemas, [])
        self.assertIn(f"{self.versao}/{PACOTE}", historico)


class TestListaSoCresce(unittest.TestCase):
    """`--lista-so-cresce`: cada versão da lista na história do git está contida na atual."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="revisao-177-lista-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.repo = self.base / "repo"
        (self.repo / "entrega").mkdir(parents=True)
        self.lista = self.repo / "entrega" / HISTORICO
        self.git("init", "-q")
        self.vp = carregar_verificador()

    def git(self, *args) -> str:
        config = ("user.name=ensaio", "user.email=ensaio-sem-email", "commit.gpgsign=false",  # sem e-mail no texto
                  "core.hooksPath=" + str(self.base / "sem-hooks"))
        r = subprocess.run(["git", "-C", str(self.repo), *(x for c in config for x in ("-c", c)), *args],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def gravar(self, *linhas: str) -> None:
        self.lista.write_text("".join(linha + "\n" for linha in linhas), encoding="utf-8", newline="\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "lista")

    def test_acrescentar_passa_e_trocar_ou_tirar_reprova(self):
        a, b = f"{'a' * 64}  1.0.0/{PACOTE}", f"{'b' * 64}  1.0.0/{COMPLETO}"
        self.gravar(a)
        self.gravar(a, b)
        self.assertEqual(self.vp.conferir_crescimento(self.lista), [])
        self.gravar(f"{'c' * 64}  1.0.0/{PACOTE}", b)                                 # troca um hash antigo
        problemas = self.vp.conferir_crescimento(self.lista)
        self.assertTrue(any("só cresce" in p for p in problemas), problemas)

    def test_sem_historia_completa_reprova(self):
        self.gravar(f"{'a' * 64}  1.0.0/{PACOTE}")
        self.gravar(f"{'a' * 64}  1.0.0/{PACOTE}", f"{'b' * 64}  1.0.0/{COMPLETO}")
        raso = self.base / "raso"
        r = subprocess.run(["git", "clone", "-q", "--depth", "1", self.repo.as_uri(), str(raso)], capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, r.stderr)
        problemas = self.vp.conferir_crescimento(raso / "entrega" / HISTORICO)
        self.assertTrue(any("raso" in p for p in problemas), problemas)
        fora = self.base / "fora" / HISTORICO
        fora.parent.mkdir()
        fora.write_text(f"{'a' * 64}  1.0.0/{PACOTE}\n", encoding="utf-8")
        self.assertTrue(self.vp.conferir_crescimento(fora))                           # fora de um repositório


class TestEmpacotadorAcrescentaALista(unittest.TestCase):
    """O empacotar.py acrescenta os pacotes novos à lista e recusa reempacotar uma versão já liberada com outro
    conteúdo (suba a versão)."""

    setUp = base_177.TestN6Empacotador.setUp
    rodar = base_177.TestN6Empacotador.rodar
    dubla_package_skill = staticmethod(base_177.TestN6Empacotador.dubla_package_skill)

    def test_pacotes_novos_vao_para_a_lista_e_a_versao_liberada_nao_muda(self):
        for p in self.dist.iterdir():
            p.unlink()
        rc = self.rodar(self.dubla_package_skill())
        self.assertEqual(rc, 0, self.saida[-600:])
        lista = self.dist.parent / HISTORICO
        historico, problemas = carregar_verificador().ler_historico(lista)
        self.assertEqual(problemas, [])
        self.assertEqual(historico, {f"9.9.9/{n}": sha((self.dist / n).read_bytes()) for n in (PACOTE, COMPLETO)})
        res = carregar_verificador().verificar(self.dist, self.skill, exigir_igual_a_arvore=True)
        self.assertTrue(res["ok"], res["problemas"][:10])
        antes = {p.name: p.read_bytes() for p in self.dist.iterdir() if p.is_file()}
        texto = lista.read_bytes()
        (self.skill / "references" / "nota.md").write_bytes(b"nota mudada sem subir a versao\n")
        rc = self.rodar(self.dubla_package_skill())
        self.assertEqual(rc, 1, self.saida[-600:])
        self.assertIn("9.9.9", self.saida)
        self.assertEqual({p.name: p.read_bytes() for p in self.dist.iterdir() if p.is_file()}, antes)
        self.assertEqual(lista.read_bytes(), texto)


class TestCIPublicaRigida(unittest.TestCase):
    def test_ci_exige_a_transferencia_e_a_lista_que_so_cresce_com_a_historia_inteira(self):
        texto = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("python -B entrega/verificar_pacote.py --exigir-igual-a-arvore --exigir-transferencia "
                      "--lista-so-cresce", texto)
        self.assertRegex(texto, r"fetch-depth:\s*0")


if __name__ == "__main__":
    unittest.main()
