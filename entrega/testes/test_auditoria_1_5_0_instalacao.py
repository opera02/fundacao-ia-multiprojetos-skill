"""Auditoria externa sobre a 1.4.1 (A01–A02) e varredura da 1.4.5 (#1–#3): instalação e empacotamento.

- #2 (origem autenticada): `instalar`/`atualizar` exigem `--sha256` para pacote; o `SHA256SUMS.txt` ao lado não
  autentica (viaja no mesmo canal); pasta só com `--pasta-de-desenvolvimento-nao-verificada`, que avisa na saída.
- #3 (mesmos bytes): o pacote trocado no disco logo depois do hash não é o que se instala.
- A01 (retorno): se a troca ou a ligação falham e o retorno à versão anterior TAMBÉM falha, a saída não diz que a
  anterior ficou no lugar e informa onde ela está.
- A02 (identidade e fronteiras): `remover` e `atualizar` não retiram pasta física que não declara esta skill;
  ligação na pasta de origem é recusada; o pacote é conferido antes de extrair (nomes que o Windows apelida ou
  descarta, componentes ambíguos, duplicatas, link simbólico, limites de entradas e de tamanho).
- #1 (empacotamento): ligação na árvore da skill recusa o empacotamento, em vez de publicar o alvo dela.

Perfis DESCARTÁVEIS (USERPROFILE e HOME temporários, conferidos antes) e dados fictícios. Falham no instalador e no
empacotador da 1.4.5 (menos os controles, indicados) e passam na 1.5.0. Ligação de pasta: junção no Windows (sem
privilégio), link simbólico nos demais. Link simbólico de ARQUIVO no Windows exige privilégio: sem ele o teste é
pulado, e a mesma regra é coberta por uma ligação simulada (`Path.is_symlink`).
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import os
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

from test_auditoria_final_1_4_2 import _Preparo
from test_auditoria_1_4_1 import NOME
from test_empacotar import carregar_modulo as carregar_empacotador
from test_instalar_skill import carregar_modulo as carregar_instalador
from test_relatorio_tecnico_1_4_0 import OPCAO_PASTA_DEV

OUTRA_SKILL_MD = "---\nname: outra-skill\ndescription: x\n---\n"

# O atacante troca o pacote no disco logo depois de o hash ser calculado (#3).
TROCA_DEPOIS_DO_HASH = r"""
import hashlib, os, shutil
_sha256 = hashlib.sha256
_feito = []
class _Hash:
    def __init__(self, *a, **k):
        self._h = _sha256(*a, **k)
    def update(self, dados):
        self._h.update(dados)
    def digest(self):
        return self._h.digest()
    def hexdigest(self):
        h = self._h.hexdigest()
        if h == os.environ["TESTE_HASH_LEGITIMO"] and not _feito:
            _feito.append(1)
            shutil.copyfile(os.environ["TESTE_PACOTE_TROCADO"], os.environ["TESTE_PACOTE"])
        return h
hashlib.sha256 = _Hash
"""
# A troca (skills-preparo -> skills) e o retorno (skills-anteriores -> skills) falham (A01).
FALHA_NA_TROCA_E_NO_RETORNO = """
import os
_replace = os.replace
def _r(src, dst, *a, **k):
    pasta = os.path.basename(os.path.dirname(str(src)))
    if pasta in ('skills-preparo', 'skills-anteriores'):
        raise OSError(5, 'falha simulada em ' + pasta)
    return _replace(src, dst, *a, **k)
os.replace = _r
"""
# A criação da ligação falha (junção ou link simbólico).
FALHA_NA_LIGACAO = """
import os, subprocess
_run = subprocess.run
def _sem_juncao(cmd, *a, **k):
    if isinstance(cmd, list) and 'mklink' in cmd:
        raise OSError(5, 'falha simulada ao criar a ligacao')
    return _run(cmd, *a, **k)
subprocess.run = _sem_juncao
def _sem_symlink(*a, **k):
    raise OSError(5, 'falha simulada ao criar a ligacao')
os.symlink = _sem_symlink
"""
# O retorno da versão anterior (skills-anteriores -> skills) falha.
FALHA_NO_RETORNO = """
import os
_replace_r = os.replace
def _r2(src, dst, *a, **k):
    if os.path.basename(os.path.dirname(str(src))) == 'skills-anteriores':
        raise OSError(5, 'falha simulada no retorno')
    return _replace_r(src, dst, *a, **k)
os.replace = _r2
"""
# Nomes que o Windows apelida (troca `<>:"|?*` por `_`, tira ponto/espaço do fim) ou descarta (dispositivos).
NOMES_NAO_PORTAVEIS = ["scripts/a?.py", "scripts/a*.py", "scripts/a:b.py", 'scripts/a"b.py', "scripts/a<b.py",
                       "scripts/a|b.py", "references/nota.md.", "references/nota.md ", "references/a\x01b.md",
                       "references/nul", "references/CON.txt", "references/Com1.md", "references/lpt\u00b9.md",
                       "references/aux .md"]


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def ligar_pasta(link: Path, alvo: Path, caso: unittest.TestCase) -> None:
    """Junção no Windows (sem privilégio); link simbólico de pasta nos demais."""
    link.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(alvo)], capture_output=True, text=True,
                           errors="replace")
        if r.returncode != 0:
            caso.skipTest(f"junção indisponível: {r.stdout.strip()} {r.stderr.strip()}")
    else:
        link.symlink_to(alvo, target_is_directory=True)


def simular_link(alvo: Path):
    """`Path.is_symlink` verdadeiro para `alvo`: cobre a regra do link de arquivo sem privilégio no Windows."""
    original = Path.is_symlink
    return mock.patch.object(Path, "is_symlink", lambda p: Path(p) == alvo or original(p))


class _Instalacao(_Preparo):
    def pacote(self, origem: Path, rotulo: str, extra=()) -> Path:
        """Pacote fictício de `origem` com as entradas `extra` (nome ou ZipInfo, conteúdo) no fim."""
        destino = self.base / f"pacote-{rotulo}" / f"{NOME}.skill"
        destino.parent.mkdir(parents=True, exist_ok=True)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # nome duplicado, quando houver, é de propósito
            with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
                for p in sorted(origem.rglob("*")):
                    if p.is_file():
                        z.write(p, f"{NOME}/{p.relative_to(origem).as_posix()}")
                for nome, conteudo in extra:
                    z.writestr(nome, conteudo)
        return destino

    def sem_instalacao(self) -> None:
        """Volta o perfil descartável ao estado sem a skill (entre subcasos)."""
        if os.path.lexists(self.link):
            os.rmdir(self.link) if os.name == "nt" else self.link.unlink()
        shutil.rmtree(self.perfil / ".agents", ignore_errors=True)

    def remover_ligacao(self) -> None:
        os.rmdir(self.link) if os.name == "nt" else self.link.unlink()

    def instalar_v1(self) -> None:
        p, _ = self.rodar("instalar", "--origem", self.pacote(self.nova_origem("v1", "versao-1"), "v1"))
        self.assertEqual(p.returncode, 0, p.stdout[-500:] + p.stderr[-500:])


class TestN2OrigemAutenticada(_Instalacao):
    """Na 1.4.5, pacote sem hash, pacote com um SHA256SUMS.txt forjado ao lado e pasta qualquer eram instalados."""

    def test_n2_pacote_sem_sha256_e_recusado_sem_alterar(self):
        pacote = self.pacote(self.origem, "sem-hash")
        for acao in ("instalar", "atualizar"):
            with self.subTest(acao):
                p, saida = self.rodar(acao, "--origem", pacote, autenticar=False)
                self.assertNotEqual(p.returncode, 0, "instalou um pacote sem hash recebido por outro canal")
                self.assertFalse(self.copia.exists())
                self.assertFalse(os.path.lexists(self.link))
                self.assertIn("--sha256", (saida or {}).get("erro", ""), saida)

    def test_n2_sha256sums_ao_lado_nao_substitui_o_hash_independente(self):
        pacote = self.pacote(self.nova_origem("forjada", "FORJADA"), "forjado")
        (pacote.parent / "SHA256SUMS.txt").write_text(f"{sha256(pacote)}  {pacote.name}\n", encoding="utf-8")
        p, saida = self.rodar("instalar", "--origem", pacote, autenticar=False)
        self.assertNotEqual(p.returncode, 0, "o SHA256SUMS.txt do mesmo canal bastou para instalar")
        self.assertIsNone(self.descricao_instalada())
        self.assertNotIn("Traceback", p.stderr)

    def test_n2_verificar_sem_sha256_nao_da_o_pacote_por_autenticado(self):
        pacote = self.pacote(self.origem, "verificar")
        (pacote.parent / "SHA256SUMS.txt").write_text(f"{sha256(pacote)}  {pacote.name}\n", encoding="utf-8")
        p, _ = self.rodar("instalar", "--origem", pacote)
        self.assertEqual(p.returncode, 0, p.stdout[-500:] + p.stderr[-500:])
        p, saida = self.rodar("verificar", "--origem", pacote, autenticar=False)
        integridade = (saida or {}).get("integridade_do_pacote") or {}
        self.assertIsNot(integridade.get("ok"), True, "SHA256SUMS.txt ao lado apresentado como verificação")
        self.assertIn("SHA256SUMS.txt", integridade.get("conferido_com", []), "deixou de conferir a consistência")
        self.assertEqual((saida or {}).get("divergentes"), [], saida)
        p, saida = self.rodar("verificar", "--origem", pacote, "--sha256", sha256(pacote), autenticar=False)
        self.assertIs(((saida or {}).get("integridade_do_pacote") or {}).get("ok"), True, saida)

    def test_n2_pasta_sem_a_opcao_de_desenvolvimento_e_recusada(self):
        for acao in ("instalar", "atualizar"):
            with self.subTest(acao):
                p, saida = self.rodar(acao, "--origem", self.origem, autenticar=False)
                self.assertNotEqual(p.returncode, 0, "instalou uma pasta sem verificação")
                self.assertFalse(self.copia.exists())
                self.assertIn(OPCAO_PASTA_DEV, (saida or {}).get("erro", ""), saida)

    def test_n2_pasta_com_a_opcao_de_desenvolvimento_instala_e_avisa(self):
        p, saida = self.rodar("instalar", "--origem", self.origem, OPCAO_PASTA_DEV, autenticar=False)
        self.assertEqual(p.returncode, 0, p.stdout[-500:] + p.stderr[-500:])
        self.assertIn("NÃO VERIFICADA", (saida or {}).get("aviso", ""), saida)
        self.assertIsNone(((saida or {}).get("integridade_do_pacote") or {}).get("ok", "ausente"))

    def test_n2_controle_quem_ja_passa_sha256_segue_igual(self):
        """Controle (passa na 1.4.5 e na 1.5.0): hash informado, também em maiúsculas."""
        pacote = self.pacote(self.origem, "com-hash")
        p, saida = self.rodar("instalar", "--origem", pacote, "--sha256", sha256(pacote).upper(), autenticar=False)
        self.assertEqual(p.returncode, 0, p.stdout[-500:] + p.stderr[-500:])
        integridade = (saida or {}).get("integridade_do_pacote") or {}
        self.assertIs(integridade.get("ok"), True, saida)
        self.assertIn("--sha256", integridade.get("conferido_com", []))


class TestN3MesmosBytes(_Instalacao):
    """Na 1.4.5, o hash era do caminho: o pacote trocado depois da conferência era o extraído e instalado."""

    def test_n3_pacote_trocado_depois_do_hash_nao_e_o_instalado(self):
        legitimo = self.pacote(self.nova_origem("legitima", "LEGITIMA"), "legitimo")
        trocado = self.pacote(self.nova_origem("trocada", "TROCADA"), "trocado")
        h = sha256(legitimo)
        self.env.update(TESTE_HASH_LEGITIMO=h, TESTE_PACOTE=str(legitimo), TESTE_PACOTE_TROCADO=str(trocado))
        p, saida = self.rodar("instalar", "--origem", legitimo, "--sha256", h, preludio=TROCA_DEPOIS_DO_HASH)
        self.assertNotEqual(sha256(legitimo), h, "a troca simulada do pacote não aconteceu")
        self.assertNotEqual(self.descricao_instalada(), "TROCADA", "instalou bytes diferentes dos conferidos")
        self.assertEqual(p.returncode, 0, p.stdout[-500:] + p.stderr[-500:])
        self.assertEqual(self.descricao_instalada(), "LEGITIMA")


class TestA01RetornoQueFalha(_Instalacao):
    """Na 1.4.5, com o retorno também falhando, a saída dizia que a versão instalada era "mantida ou devolvida ao
    lugar" e não dizia onde estava a anterior (que tinha saído do lugar)."""

    def conferir_relato(self, p, saida) -> None:
        self.assertNotEqual(p.returncode, 0)
        self.assertIsNotNone(saida, f"saída não é JSON: {p.stderr[-300:]}")
        self.assertNotIn("mantida ou devolvida", saida.get("erro", ""), "falha do retorno relatada como retorno")
        anterior = Path(saida.get("versao_anterior_em") or self.base / "nao-informada")
        self.assertTrue((anterior / "SKILL.md").is_file(), f"lugar da versão anterior não informado: {saida}")
        self.assertIn("versao-1", (anterior / "SKILL.md").read_text(encoding="utf-8"))

    def test_a01_troca_e_retorno_que_falham_dizem_onde_esta_a_anterior(self):
        self.instalar_v1()
        v2 = self.pacote(self.nova_origem("v2", "versao-2"), "v2")
        p, saida = self.rodar("atualizar", "--origem", v2, preludio=FALHA_NA_TROCA_E_NO_RETORNO)
        self.conferir_relato(p, saida)
        p, saida = self.rodar("atualizar", "--origem", v2)  # a ação indicada: concluir a troca
        self.assertEqual(p.returncode, 0, p.stdout[-500:] + p.stderr[-500:])
        self.assertEqual(self.descricao_instalada(), "versao-2")
        self.assertTrue((self.link / "SKILL.md").exists())

    def test_a01_ligacao_e_retorno_que_falham_dizem_onde_esta_a_anterior(self):
        self.instalar_v1()
        self.remover_ligacao()
        v2 = self.pacote(self.nova_origem("v2", "versao-2"), "v2")
        p, saida = self.rodar("atualizar", "--origem", v2, preludio=FALHA_NA_LIGACAO + FALHA_NO_RETORNO)
        self.conferir_relato(p, saida)

    def test_a01_controle_falha_na_ligacao_devolve_a_anterior(self):
        """Controle (passa na 1.4.5 e na 1.5.0)."""
        self.instalar_v1()
        self.remover_ligacao()
        v2 = self.pacote(self.nova_origem("v2", "versao-2"), "v2")
        p, saida = self.rodar("atualizar", "--origem", v2, preludio=FALHA_NA_LIGACAO)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(self.descricao_instalada(), "versao-1", "a versão anterior não voltou ao lugar")
        self.assertEqual(self.sobras(), [])

    def test_a01_controle_atualizar_a_partir_da_propria_copia(self):
        """Controle (passa na 1.4.5 e na 1.5.0): a cópia nova é preparada antes de a ativa sair do lugar."""
        self.instalar_v1()
        p, saida = self.rodar("atualizar", "--origem", self.copia)
        self.assertEqual(p.returncode, 0, p.stdout[-500:] + p.stderr[-500:])
        self.assertEqual(self.descricao_instalada(), "versao-1")
        self.assertTrue((self.link / "SKILL.md").exists())


class TestA02IdentidadeDoDestino(_Instalacao):
    """Na 1.4.5, `remover --confirmar` apagava a pasta física em ~/.agents/skills sem conferir o `name` (o que já
    se fazia em ~/.claude/skills), e `atualizar` a tirava do lugar como se fosse a versão anterior desta skill."""

    def pasta_de_outra_skill(self) -> None:
        self.copia.mkdir(parents=True)
        (self.copia / "SKILL.md").write_text(OUTRA_SKILL_MD, encoding="utf-8")
        (self.copia / "trabalho.txt").write_text("dados fictícios do usuário", encoding="utf-8")

    def test_a02_remover_mantem_pasta_fisica_que_nao_e_desta_skill(self):
        self.pasta_de_outra_skill()
        p, saida = self.rodar("remover", "--confirmar")
        self.assertTrue((self.copia / "trabalho.txt").exists(), "apagou uma pasta que não declara esta skill")
        self.assertNotEqual(p.returncode, 0, "saiu com sucesso deixando a pasta no lugar")
        self.assertFalse((saida or {}).get("removido"), saida)
        self.assertTrue(any(m.get("caminho") == str(self.copia) and m.get("acao") == "manter"
                            for m in (saida or {}).get("mantidos", [])), saida)

    def test_a02_atualizar_recusa_pasta_fisica_que_nao_e_desta_skill(self):
        self.pasta_de_outra_skill()
        p, saida = self.rodar("atualizar", "--origem", self.pacote(self.nova_origem("v1", "versao-1"), "v1"))
        self.assertNotEqual(p.returncode, 0, "trocou uma pasta que não declara esta skill")
        self.assertEqual(self.descricao_instalada(), "x", "a pasta da outra skill saiu do lugar")
        self.assertTrue((self.copia / "trabalho.txt").exists())
        self.assertFalse((self.perfil / ".agents" / "skills-anteriores").exists())
        self.assertIn("name", (saida or {}).get("erro", ""), saida)


class TestA02LigacaoNaOrigem(_Instalacao):
    """Na 1.4.5, a cópia da pasta de origem seguia ligações e trazia para a instalação o conteúdo de fora dela."""

    def externo(self) -> Path:
        externo = self.base / "externo-privado"
        externo.mkdir()
        (externo / "segredo.txt").write_text("CONTEUDO-PRIVADO-FICTICIO", encoding="utf-8")
        return externo

    def conferir_recusa(self, p, saida) -> None:
        self.assertNotEqual(p.returncode, 0, "instalou uma origem com ligação para fora dela")
        self.assertFalse(self.copia.exists())
        self.assertIn("ligação", (saida or {}).get("erro", ""), saida)

    def test_a02_pasta_ligada_para_fora_da_origem_e_recusada(self):
        externo = self.externo()
        ligar_pasta(self.origem / "references" / "anexos", externo, self)
        p, saida = self.rodar("instalar", "--origem", self.origem)
        self.conferir_recusa(p, saida)
        self.assertTrue((externo / "segredo.txt").exists())

    def test_a02_link_de_arquivo_para_fora_da_origem_e_recusado(self):
        segredo = self.externo() / "segredo.txt"
        try:
            os.symlink(segredo, self.origem / "references" / "inocente.md")
        except OSError as exc:
            self.skipTest(f"link simbólico de arquivo indisponível ({exc}); coberto pela ligação simulada")
        p, saida = self.rodar("instalar", "--origem", self.origem)
        self.conferir_recusa(p, saida)

    def test_a02_link_de_arquivo_simulado_na_origem_e_recusado(self):
        mod = carregar_instalador()
        alvo = self.origem / "references" / "nota.md"
        with simular_link(alvo), self.assertRaises(mod.Recusa) as recusa:
            mod.origem_como_pasta(self.origem, self.base / "extracao")
        self.assertIn("references/nota.md", str(recusa.exception.dados), recusa.exception.dados)


class TestA02PacoteConferidoAntesDeExtrair(_Instalacao):
    """Na 1.4.5, o `extractall` sem conferência instalava o que o Windows fazia dos nomes: `a?.py` sobrescrevia
    `a_.py`, `nota.md.` sobrescrevia `nota.md`, `nul` sumia; duplicatas e `x/../y` valiam pela última entrada."""

    def conferir_recusa(self, extra, rotulo: str) -> None:
        self.sem_instalacao()
        p, saida = self.rodar("instalar", "--origem", self.pacote(self.origem, rotulo, extra))
        nomes = [n if isinstance(n, str) else n.filename for n, _ in extra]
        self.assertNotEqual(p.returncode, 0, f"instalou o pacote com {nomes!r}")
        self.assertFalse(self.copia.exists())
        self.assertIsNotNone(saida, f"saída não é JSON: {p.stderr[-300:]}")
        self.assertNotIn("Traceback", p.stderr)

    def test_a02_nomes_que_o_windows_apelida_ou_descarta_sao_recusados(self):
        for i, nome in enumerate(NOMES_NAO_PORTAVEIS):
            with self.subTest(nome=nome):
                self.conferir_recusa([(f"{NOME}/{nome}", "conteúdo fictício")], f"nome-{i}")

    def test_a02_componentes_ambiguos_sao_recusados(self):
        casos = [f"{NOME}/references/../SKILL.md", f"{NOME}//references/x.md", f"{NOME}/./references/x.md"]
        if os.sep == "/":  # no Windows o próprio zipfile já lê a barra invertida como separador
            casos.append(f"{NOME}/references\\x.md")
        for i, nome in enumerate(casos):
            with self.subTest(nome=nome):
                self.conferir_recusa([(nome, "conteúdo fictício")], f"componente-{i}")

    def test_a02_entradas_duplicadas_sao_recusadas(self):
        casos = {"mesmo-nome": [(f"{NOME}/references/nota.md", "SEGUNDA-ENTRADA")],
                 "outra-caixa": [(f"{NOME}/References/Nota.md", "OUTRA-CAIXA")],
                 "outra-forma-unicode": [(f"{NOME}/references/caf\u00e9.md", "NFC"),
                                         (f"{NOME}/references/cafe\u0301.md", "NFD")]}
        for rotulo, extra in casos.items():
            with self.subTest(rotulo):
                self.conferir_recusa(extra, rotulo)

    def test_a02_entrada_de_link_simbolico_e_recusada(self):
        info = zipfile.ZipInfo(f"{NOME}/references/atalho.md")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.conferir_recusa([(info, "../../../../segredo-do-host")], "symlink")


class TestA02LimitesDoPacote(unittest.TestCase):
    """Na 1.4.5 não havia limite: 120 MiB de zeros (122 KB compactados) foram extraídos e instalados. Aqui os
    limites são reduzidos no módulo carregado, para o teste ser leve; nada toca o perfil."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="instalar-skill-limites-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.mod = carregar_instalador()

    def pacote(self, conteudos: dict[str, bytes]) -> Path:
        destino = self.base / f"{NOME}-{len(list(self.base.iterdir()))}.skill"
        with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(f"{NOME}/SKILL.md", f"---\nname: {NOME}\ndescription: limites\n---\n")
            for nome, dados in conteudos.items():
                z.writestr(f"{NOME}/{nome}", dados)
        return destino

    def conferir_recusa(self, pacote: Path, **limites) -> None:
        extracao = self.base / f"extracao-{pacote.stem}"
        with contextlib.ExitStack() as pilha:
            for nome, valor in limites.items():
                pilha.enter_context(mock.patch.object(self.mod, nome, valor, create=True))
            with self.assertRaises(self.mod.Recusa):
                self.mod.origem_como_pasta(pacote, extracao)
        extraidos = [p for p in extracao.rglob("*") if p.is_file()] if extracao.exists() else []
        self.assertEqual(extraidos, [], "extraiu antes de recusar")

    def test_a02_entradas_demais_sao_recusadas(self):
        self.conferir_recusa(self.pacote({f"references/{i}.md": b"x" for i in range(5)}), LIMITE_ENTRADAS=5)

    def test_a02_tamanho_descompactado_demais_e_recusado(self):
        self.conferir_recusa(self.pacote({"references/zeros.bin": bytes(1024 * 1024)}), LIMITE_BYTES=256 * 1024)

    def test_a02_pacote_grande_demais_e_recusado_antes_de_ler_tudo(self):
        self.conferir_recusa(self.pacote({"references/aleatorio.bin": os.urandom(300 * 1024)}),
                             LIMITE_BYTES=256 * 1024)


class TestN1EmpacotarNaoSegueLigacoes(unittest.TestCase):
    """Na 1.4.5, o zip completo seguia ligações da árvore da skill e publicava o alvo delas (aqui, um arquivo
    fictício do "computador que gera a entrega"). `dist` descartável; o skill-creator é um dublê."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="empacotar-ligacoes-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.dist = self.base / "dist"
        self.dist.mkdir()
        (self.dist / f"{NOME}.skill").write_bytes(b"PACOTE-ANTERIOR-FICTICIO")
        self.antes = {p.name: p.read_bytes() for p in self.dist.iterdir()}
        self.skill = self.base / "fonte" / NOME
        (self.skill / "evals").mkdir(parents=True)
        (self.skill / "SKILL.md").write_text(f"---\nname: {NOME}\nmetadata:\n  version: \"9.9.9\"\n---\n",
                                             encoding="utf-8")
        (self.skill / "evals" / "evals.json").write_text("{}", encoding="utf-8")
        self.host = self.base / "host"
        self.host.mkdir()
        (self.host / "credencial.txt").write_text("CREDENCIAL-FICTICIA-DO-HOST", encoding="utf-8")
        self.creator = self.base / "skill-creator"
        (self.creator / "scripts").mkdir(parents=True)
        (self.creator / "scripts" / "package_skill.py").write_text("# dublê fictício\n", encoding="utf-8")
        self.mod = carregar_empacotador()
        self.mod.DIST, self.mod.SKILL = self.dist, self.skill
        # Dublê registrado (desde a 1.7.7 só a ferramenta registrada roda; Codex Security da 1.7.6, #6): estes testes
        # tratam da ligação na árvore, recusada antes de a ferramenta rodar.
        self.mod.FERRAMENTA_ESPERADA = {
            "scripts/package_skill.py": sha256(self.creator / "scripts" / "package_skill.py")}

    def rodar(self):
        def gerar(cmd, **kw):
            with zipfile.ZipFile(Path(cmd[-1]) / f"{NOME}.skill", "w") as z:
                z.writestr(f"{NOME}/SKILL.md", "---\nname: x\n---\n")
            return subprocess.CompletedProcess(cmd, 0, "pacote fictício gerado", "")
        saida = io.StringIO()
        with mock.patch.object(self.mod.subprocess, "run", side_effect=gerar), \
                mock.patch.object(sys, "argv", ["empacotar.py", "--skill-creator", str(self.creator)]), \
                contextlib.redirect_stdout(saida), contextlib.redirect_stderr(saida):
            return self.mod.main()

    def conferir_recusa(self, rc) -> None:
        publicados = []
        for pacote in self.dist.rglob("*.zip"):
            with zipfile.ZipFile(pacote) as z:
                publicados += [n for n in z.namelist() if b"CREDENCIAL" in z.read(n)]
        self.assertEqual(publicados, [], "o pacote publicou o conteúdo do alvo da ligação")
        self.assertEqual(rc, 1, "o empacotamento seguiu com uma ligação na árvore da skill")
        for nome, dados in self.antes.items():
            self.assertEqual((self.dist / nome).read_bytes(), dados, f"{nome} mudou numa recusa")

    def test_n1_pasta_ligada_para_fora_recusa_o_empacotamento(self):
        ligar_pasta(self.skill / "references", self.host, self)
        self.conferir_recusa(self.rodar())

    def test_n1_link_de_arquivo_para_fora_recusa_o_empacotamento(self):
        try:
            os.symlink(self.host / "credencial.txt", self.skill / "inocente.md")
        except OSError as exc:
            self.skipTest(f"link simbólico de arquivo indisponível ({exc}); coberto pela ligação simulada")
        self.conferir_recusa(self.rodar())

    def test_n1_link_de_arquivo_simulado_recusa_o_empacotamento(self):
        with simular_link(self.skill / "evals" / "evals.json"):
            rc = self.rodar()
        self.assertEqual(rc, 1, "o empacotamento seguiu com uma ligação (simulada) na árvore da skill")


if __name__ == "__main__":
    unittest.main()
