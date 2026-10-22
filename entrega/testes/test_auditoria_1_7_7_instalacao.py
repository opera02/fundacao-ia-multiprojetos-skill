"""Auditoria de segurança da 1.7.6 (Codex Security, 21/10/2026), achado #4 — `instalar_skill.py`: a marca da troca
interrompida (`~/.agents/skills-preparo/troca-em-andamento.json`) não autoriza mexer em caminho nenhum.

Na 1.7.6 a recuperação lia da marca os caminhos absolutos `preparo` e `anterior` e os passava a `shutil.rmtree` e a
`os.replace` sem conferir nada: uma marca plantada apagava uma pasta qualquer do usuário (com a skill instalada) ou
punha uma pasta qualquer no lugar da skill (sem ela). Desde a 1.7.7 a marca guarda só identificadores (o nome que o
próprio instalador dá às cópias), o destino tem de ser o fixo, as pastas indicadas têm de ser pastas comuns direto sob
skills-preparo e skills-anteriores (que também não podem ser ligação), a versão anterior só volta ao lugar com o `name`
e o hash da árvore gravados na marca, e a cópia preparada nunca vira a skill a partir da marca. O resto recusa sem
mover nem apagar nada, e a marca fica para o titular conferir.

Perfis DESCARTÁVEIS (USERPROFILE e HOME temporários, conferidos antes) e dados fictícios. A "vítima" é uma pasta fora
das áreas do instalador que declara `name: fundacao-ia-multiprojetos`: assim só a regra de contenção a protege. Ligação
real: junção no Windows (sem privilégio), link simbólico nos demais; o link simbólico no Windows é simulado no processo
filho (`Path.is_symlink`), sem pular teste. Falham no instalador da 1.7.6 (menos os controles, indicados) e passam na
1.7.7.
"""

from __future__ import annotations

import json
import os
import re
import unittest
from pathlib import Path

from test_auditoria_1_4_1 import NOME, skill_md
from test_auditoria_1_5_0_instalacao import _Instalacao, ligar_pasta
from test_auditoria_final_1_4_2 import QUEDA_ENTRE_AS_RENOMEACOES
from test_instalar_skill import carregar_modulo as carregar_instalador

ID = f"{NOME}-20260101-000000"  # nome no formato que o instalador dá às cópias (caminho_livre)
PADRAO_ID = re.compile(re.escape(NOME) + r"-[0-9]{8}-[0-9]{6}(-[0-9]+)?")

# Link simbólico simulado no processo filho: `Path.is_symlink` verdadeiro para o caminho em TESTE_LINK_SIMULADO (o
# Windows sem modo de desenvolvedor não cria link simbólico; a junção real fica com o outro teste).
SIMULAR_LINK = """
import os, pathlib
_simulado = os.path.normcase(os.environ["TESTE_LINK_SIMULADO"])
_is_symlink = pathlib.Path.is_symlink
pathlib.Path.is_symlink = lambda p, *a, **k: os.path.normcase(str(p)) == _simulado or _is_symlink(p, *a, **k)
"""


class _Recuperacao(_Instalacao):
    def setUp(self):
        super().setUp()
        self.v2 = self.pacote(self.nova_origem("v2", "versao-2"), "v2")

    @property
    def anteriores(self) -> Path:
        return self.perfil / ".agents" / "skills-anteriores"

    @property
    def marca(self) -> Path:
        return self.preparo / "troca-em-andamento.json"

    def nova_vitima(self, rotulo: str) -> Path:
        """Pasta do usuário fora das áreas do instalador, que declara esta skill (só a contenção a protege)."""
        vitima = self.base / f"vitima-{rotulo}"
        vitima.mkdir(parents=True)
        (vitima / "SKILL.md").write_text(skill_md(f"VITIMA-{rotulo}"), encoding="utf-8")
        (vitima / "dados.txt").write_text("dados fictícios do usuário", encoding="utf-8")
        return vitima

    @staticmethod
    def conteudo(pasta: Path) -> dict:
        return {p.relative_to(pasta).as_posix(): p.read_bytes() for p in sorted(pasta.rglob("*")) if p.is_file()}

    def plantar(self, **campos) -> None:
        """Marca no formato da 1.7.7, válida em tudo menos no que o teste muda: cada teste exercita uma regra."""
        dados = {"versao_marca": 2, "preparo": ID, "anterior": None, "destino": str(self.copia),
                 "arvore_anterior": None, "inicio": "2026-01-01T00:00:00"}
        dados.update(campos)
        if dados["anterior"] is not None and dados["arvore_anterior"] is None:
            dados["arvore_anterior"] = "0" * 64
        self.marca.parent.mkdir(parents=True, exist_ok=True)
        self.marca.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")

    def queda_no_meio_da_troca(self) -> dict:
        """v1 instalada e queda entre as duas renomeações da atualização para a v2: devolve a marca legítima."""
        self.instalar_v1()
        self.rodar("atualizar", "--origem", self.v2, preludio=QUEDA_ENTRE_AS_RENOMEACOES)
        self.assertFalse(os.path.lexists(self.copia), "a queda entre as renomeações não se reproduziu")
        self.assertTrue(self.marca.is_file(), "a marca de troca não ficou na área de preparo")
        return json.loads(self.marca.read_text(encoding="utf-8"))

    def foto(self) -> dict:
        """Conteúdo das áreas do instalador (para conferir que uma recusa não mexeu em nada)."""
        return {str(p): self.conteudo(p) for p in (self.preparo, self.anteriores) if p.is_dir()}

    def sem_a_skill(self) -> None:
        """Perfil sem esta skill, mas com a pasta de skills (onde ficam as outras skills do usuário)."""
        self.sem_instalacao()
        self.copia.parent.mkdir(parents=True)

    def recusou_sem_mexer(self, p, saida, intactas: dict) -> None:
        for pasta, antes in intactas.items():
            self.assertTrue(Path(pasta).is_dir(), f"{pasta} foi movida ou apagada")
            self.assertEqual(self.conteudo(Path(pasta)), antes, f"{pasta} mudou")
        self.assertNotEqual(p.returncode, 0, "a recuperação agiu sobre uma marca que não é deste instalador")
        self.assertIsNotNone(saida, f"saída não é JSON: {p.stdout[-300:]} {p.stderr[-300:]}")
        self.assertIn("marca", saida.get("erro", ""), saida)
        self.assertNotIn("Traceback", p.stderr)
        self.assertTrue(self.marca.is_file(), "a marca sumiu: o titular precisa poder conferi-la")


class TestN4CaminhoNaMarca(_Recuperacao):
    """Na 1.7.6, o caminho absoluto da marca era apagado (skill instalada) ou movido para o lugar da skill."""

    def test_n4_caminho_absoluto_com_a_skill_instalada_nao_apaga_a_pasta(self):
        self.instalar_v1()
        vitima = self.nova_vitima("apagada")
        antes = self.conteudo(vitima)
        self.plantar(preparo=str(vitima))
        p, saida = self.rodar("atualizar", "--origem", self.v2)
        self.recusou_sem_mexer(p, saida, {vitima: antes})
        self.assertEqual(self.descricao_instalada(), "versao-1", "a versão instalada mudou numa recusa")
        p, saida = self.rodar("verificar")
        troca = (saida or {}).get("troca_interrompida") or {}
        self.assertIs(troca.get("marca_valida"), False, saida)
        self.assertTrue(troca.get("motivo"), saida)

    def test_n4_caminho_absoluto_sem_a_skill_instalada_nao_vira_a_skill(self):
        for campo in ("preparo", "anterior"):
            with self.subTest(campo=campo):
                self.sem_a_skill()
                vitima = self.nova_vitima(f"movida-{campo}")
                antes = self.conteudo(vitima)
                self.plantar(**{"preparo": ID, campo: str(vitima)})
                p, saida = self.rodar("instalar", "--origem", self.v2)
                self.recusou_sem_mexer(p, saida, {vitima: antes})
                self.assertFalse(os.path.lexists(self.copia), "algo foi posto no lugar da skill")
                self.assertFalse(os.path.lexists(self.link))

    def test_n4_componente_pai_nao_sai_da_area_de_preparo(self):
        self.instalar_v1()
        vitima = self.nova_vitima("acima")
        antes = self.conteudo(vitima)
        subir = os.path.join("..", "..", "..", vitima.name)  # skills-preparo -> .agents -> perfil -> base
        for valor in (os.path.join(str(self.preparo), subir), subir, f"{ID}/../../../{vitima.name}"):
            with self.subTest(valor=valor):
                self.plantar(preparo=valor)
                p, saida = self.rodar("atualizar", "--origem", self.v2)
                self.recusou_sem_mexer(p, saida, {vitima: antes})
                self.assertEqual(self.descricao_instalada(), "versao-1")

    def test_n4_prefixo_errado_e_recusado(self):
        self.instalar_v1()
        intactas = {}
        for raiz in (self.preparo, self.anteriores):
            alheia = raiz / "dados-do-usuario"
            alheia.mkdir(parents=True)
            (alheia / "planilha.txt").write_text("dados fictícios", encoding="utf-8")
            intactas[alheia] = self.conteudo(alheia)
        casos = [("preparo", "dados-do-usuario"), ("preparo", str(self.preparo / "dados-do-usuario")),
                 ("anterior", "dados-do-usuario"), ("anterior", str(self.anteriores / "dados-do-usuario")),
                 ("preparo", NOME), ("preparo", f"{NOME}-x"), ("preparo", f"{ID}-a"), ("preparo", f" {ID}")]
        for campo, valor in casos:
            with self.subTest(campo=campo, valor=valor):
                self.plantar(**{"preparo": ID, campo: valor})
                p, saida = self.rodar("atualizar", "--origem", self.v2)
                self.recusou_sem_mexer(p, saida, intactas)
                self.assertEqual(self.descricao_instalada(), "versao-1")


class TestN4LigacaoNaArea(_Recuperacao):
    """Na 1.7.6, uma ligação com o nome certo era posta no lugar da skill (a skill passava a ser o alvo dela) e a área
    de preparo ligada para fora tinha as subpastas `<nome>-*` do alvo apagadas pela limpeza da marca ilegível."""

    def test_n4_juncao_ou_link_simbolico_com_o_nome_certo_nao_e_seguido(self):
        self.sem_a_skill()
        alvo = self.nova_vitima("ligada")
        antes = self.conteudo(alvo)
        ligacao = self.preparo / ID
        ligar_pasta(ligacao, alvo, self)  # junção no Windows, link simbólico nos demais
        e_ligacao = carregar_instalador().e_ligacao
        for valor in (ID, str(ligacao)):
            with self.subTest(valor=valor):
                self.plantar(preparo=valor)
                p, saida = self.rodar("instalar", "--origem", self.v2)
                self.recusou_sem_mexer(p, saida, {alvo: antes})
                self.assertTrue(e_ligacao(ligacao), "a ligação saiu da área de preparo")
                self.assertFalse(os.path.lexists(self.copia), "a ligação foi posta no lugar da skill")

    def test_n4_link_simbolico_simulado_com_o_nome_certo_nao_e_seguido(self):
        self.sem_a_skill()
        pasta = self.preparo / ID  # pasta comum que o processo filho vê como link simbólico
        pasta.mkdir(parents=True)
        (pasta / "SKILL.md").write_text(skill_md("LINK-SIMULADO"), encoding="utf-8")
        antes = self.conteudo(pasta)
        self.env["TESTE_LINK_SIMULADO"] = str(pasta)
        for valor in (ID, str(pasta)):
            with self.subTest(valor=valor):
                self.plantar(preparo=valor)
                p, saida = self.rodar("instalar", "--origem", self.v2, preludio=SIMULAR_LINK)
                self.recusou_sem_mexer(p, saida, {pasta: antes})
                self.assertFalse(os.path.lexists(self.copia), "o link simulado foi posto no lugar da skill")

    def test_n4_area_de_preparo_ou_de_anteriores_ligada_para_fora_e_recusada(self):
        for area in ("preparo", "anteriores"):
            with self.subTest(area=area):
                self.sem_a_skill()
                fora = self.base / f"fora-{area}"  # pasta do usuário com uma subpasta de nome igual ao das cópias
                (fora / ID).mkdir(parents=True)
                (fora / ID / "SKILL.md").write_text(skill_md(f"FORA-{area}"), encoding="utf-8")
                (fora / ID / "dados.txt").write_text("dados fictícios do usuário", encoding="utf-8")
                raiz = self.preparo if area == "preparo" else self.anteriores
                ligar_pasta(raiz, fora, self)
                if area == "preparo":  # marca ilegível: a limpeza das sobras (CF-04) varreria o alvo da ligação
                    self.marca.write_text("{nao-json", encoding="utf-8")
                else:
                    self.plantar(preparo=f"{NOME}-20260101-000001", anterior=str(raiz / ID))
                antes = self.conteudo(fora)
                p, saida = self.rodar("instalar", "--origem", self.v2)
                self.recusou_sem_mexer(p, saida, {fora: antes})
                self.assertFalse(os.path.lexists(self.copia), "o alvo da ligação foi posto no lugar da skill")


class TestN4MarcaLegitima(_Recuperacao):
    """A marca gravada pelo instalador e a recuperação da queda entre as duas renomeações."""

    def test_n4_marca_guarda_identificadores_e_nao_caminhos(self):
        marca = self.queda_no_meio_da_troca()
        for campo in ("preparo", "anterior"):
            self.assertRegex(str(marca.get(campo)), r"\A" + PADRAO_ID.pattern + r"\Z", f"{campo} não é identificador")
        self.assertEqual(marca.get("destino"), str(self.copia))
        self.assertRegex(str(marca.get("arvore_anterior")), r"\A[0-9a-f]{64}\Z", "sem o hash da árvore anterior")

    def test_n4_destino_diferente_do_fixo_e_recusado(self):
        marca = self.queda_no_meio_da_troca()
        marca["destino"] = str(self.base / "outro-destino" / NOME)
        self.marca.write_text(json.dumps(marca, ensure_ascii=False), encoding="utf-8")
        antes = self.foto()
        p, saida = self.rodar("atualizar", "--origem", self.v2)
        self.recusou_sem_mexer(p, saida, {k: v for k, v in antes.items()})
        self.assertFalse(os.path.lexists(self.copia), "a troca foi concluída com uma marca de outro destino")
        self.assertFalse((self.base / "outro-destino").exists())

    def test_n4_versao_anterior_com_hash_divergente_nao_volta_ao_lugar(self):
        self.queda_no_meio_da_troca()
        anterior = next(p for p in self.anteriores.iterdir() if p.is_dir())
        (anterior / "references" / "nota.md").write_text("ALTERADA DEPOIS DA QUEDA", encoding="utf-8")
        antes = self.foto()
        p, saida = self.rodar("atualizar", "--origem", self.v2)
        self.recusou_sem_mexer(p, saida, antes)
        self.assertFalse(os.path.lexists(self.copia), "voltou ao lugar uma versão anterior que não é a que saiu")

    def test_n4_copia_preparada_nunca_e_promovida_pela_marca(self):
        """A queda foi na troca para a v2; o comando seguinte instala a v3. A cópia preparada da v2 é descartada
        (não vira a skill nem a "versão anterior"), e a anterior de verdade (v1) volta e é guardada."""
        self.queda_no_meio_da_troca()
        v3 = self.pacote(self.nova_origem("v3", "versao-3"), "v3")
        p, saida = self.rodar("atualizar", "--origem", v3)
        self.assertEqual(p.returncode, 0, p.stdout[-500:] + p.stderr[-500:])
        self.assertEqual(self.descricao_instalada(), "versao-3")
        self.assertTrue((self.link / "SKILL.md").exists(), "a ligação ficou pendurada")
        self.assertEqual(self.sobras(), [])
        guardadas = sorted((p / "SKILL.md").read_text(encoding="utf-8") for p in self.anteriores.iterdir())
        self.assertFalse(any("versao-2" in s for s in guardadas), f"a cópia preparada foi promovida: {guardadas}")
        self.assertTrue(any("versao-1" in s for s in guardadas), f"a versão anterior se perdeu: {guardadas}")

    def test_n4_controle_queda_legitima_resolvida_pelo_proximo_comando(self):
        """Controle (passa na 1.7.6 e na 1.7.7): depois da queda, o mesmo `atualizar` termina com a v2 instalada, a
        ligação de pé, a área de preparo vazia e a v1 guardada em skills-anteriores."""
        self.queda_no_meio_da_troca()
        p, saida = self.rodar("atualizar", "--origem", self.v2)
        self.assertEqual(p.returncode, 0, p.stdout[-500:] + p.stderr[-500:])
        self.assertTrue(any("troca interrompida concluída" in s for s in (saida or {}).get("passos", [])), saida)
        self.assertEqual(self.descricao_instalada(), "versao-2")
        self.assertTrue((self.link / "SKILL.md").exists())
        self.assertEqual(self.sobras(), [])
        guardadas = [(p / "SKILL.md").read_text(encoding="utf-8") for p in self.anteriores.iterdir()]
        self.assertTrue(any("versao-1" in s for s in guardadas), guardadas)


if __name__ == "__main__":
    unittest.main()
