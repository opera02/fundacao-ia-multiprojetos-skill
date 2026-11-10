"""`registry/projetos-host.json` (1.7.10; contratos do lote 2, §6; folha do HOST, item 6).

Só o titular grava (`preparo_host.py registrar-projeto`), nunca a sessão (o perfil do projeto nega `registry/`):
origens do fluxo B, pastas só de leitura e skills aninhadas negadas, por projeto. A gravação é atômica, em LF, sem
seguir ligação; a leitura tem teto e também não segue ligação. O registro só cresce, e a negação de skill vale para
todos os projetos (o que um trouxe aninhado fica negado nos outros). Pastas descartáveis; nada da raiz real.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from apoio import ENV, SKILL, criar_ligacao_dir
from test_host_projeto_apoio import carregar_preparo

AJUDANTE = SKILL / "assets" / "host" / "preparo_host.py"


def rodar(*args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", str(AJUDANTE), *map(str, args)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=ENV, timeout=120)


class Registro(unittest.TestCase):
    def setUp(self):
        self.m = carregar_preparo()
        self.base = Path(tempfile.mkdtemp(prefix="projetos-host-1710-")).resolve()
        self.raiz = self.base / "Fundacao Ensaio"
        for nome in ("caso-real", "lab-a"):
            (self.raiz / "projects" / nome).mkdir(parents=True)
        self.origem = self.base / "Origem, com vírgula"
        self.origem.mkdir()
        self.outra = self.base / "Outra Origem"
        self.outra.mkdir()
        self.arquivo = self.raiz / "registry" / "projetos-host.json"

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def test_ausente_e_o_registro_vazio(self):
        self.assertEqual(self.m.ler_projetos_host(self.raiz),
                         {"schema_version": "fundacao.projetos_host/2", "projetos": {}})  # 1.7.11: o /2 traz agentes_negados

    def test_grava_no_esquema_em_lf_e_so_cresce(self):
        self.m.registrar_projeto(self.raiz, "caso-real", [str(self.origem)], negar=["squad-a"])
        self.m.registrar_projeto(self.raiz, "caso-real", [str(self.outra)], [str(self.origem)], ["squad-a", "squad-b"])
        bruto = self.arquivo.read_bytes()
        self.assertNotIn(b"\r", bruto)
        self.assertTrue(bruto.endswith(b"\n"))
        dados = json.loads(bruto.decode("utf-8"))
        self.assertEqual(set(dados), {"schema_version", "projetos"})
        item = dados["projetos"]["caso-real"]
        self.assertEqual(set(item), {"origens", "somente_leitura", "aninhadas_negadas", "agentes_negados"})
        self.assertEqual(len(item["origens"]), 2)
        self.assertEqual(item["aninhadas_negadas"], ["squad-a", "squad-b"])
        self.assertEqual(self.m.ler_projetos_host(self.raiz), dados)
        self.assertEqual(list(self.raiz.joinpath("registry").glob(".*.tmp")), [])  # nada de temporário sobrando

    def test_recusas_antes_de_gravar(self):
        casos = {"sem origem": dict(origens=[]),
                 "pasta inexistente": dict(origens=[str(self.base / "nao-existe")]),
                 "relativa": dict(origens=["pasta/relativa"]),
                 "curinga": dict(origens=[str(self.origem) + "*"]),
                 "dentro da raiz": dict(origens=[str(self.raiz / "projects" / "lab-a")]),
                 "skill com espaço": dict(origens=[str(self.origem)], negar=["nome com espaco"]),
                 "projeto inexistente": dict(projeto="nao-existe", origens=[str(self.origem)])}
        for nome, kw in casos.items():
            with self.subTest(nome):
                projeto = kw.pop("projeto", "caso-real")
                with self.assertRaises(ValueError):
                    self.m.registrar_projeto(self.raiz, projeto, kw.pop("origens"), negar=kw.pop("negar", ()))
                self.assertFalse(self.arquivo.exists())

    def test_leitura_recusa_ligacao_forma_e_tamanho(self):
        self.m.registrar_projeto(self.raiz, "caso-real", [str(self.origem)])
        bom = self.arquivo.read_text(encoding="utf-8")
        relativo = json.loads(bom)
        relativo["projetos"]["caso-real"]["origens"] = ["relativo/pasta"]
        for nome, texto in (("chave a mais", json.dumps({**json.loads(bom), "extra": 1})),
                            ("outro esquema", bom.replace("fundacao.projetos_host/2", "fundacao.projetos_host/3")),
                            ("caminho relativo", json.dumps(relativo)),
                            ("grande demais", json.dumps({"x": "y" * (300 * 1024)}))):
            with self.subTest(nome):
                self.arquivo.write_text(texto, encoding="utf-8")
                with self.assertRaises((ValueError, OSError)):
                    self.m.ler_projetos_host(self.raiz)
        self.arquivo.write_text(bom, encoding="utf-8")
        shutil.move(str(self.raiz / "registry"), str(self.base / "registry-real"))
        criar_ligacao_dir(self.raiz / "registry", self.base / "registry-real")
        with self.assertRaises(ValueError):
            self.m.ler_projetos_host(self.raiz)

    def test_vagas_do_perfil_negacao_cumulativa(self):
        self.m.registrar_projeto(self.raiz, "caso-real", [str(self.origem)], negar=["squad-a"])
        self.m.registrar_projeto(self.raiz, "lab-a", [str(self.outra)], negar=["squad-b"])
        reg = self.m.ler_projetos_host(self.raiz)
        vagas = self.m.vagas_do_registro(reg, "caso-real")
        self.assertEqual(vagas["negar"], ["squad-a", "squad-b"])  # o de lab-a também fica negado em caso-real
        self.assertEqual(len(vagas["somente_leitura"]), 1)
        self.assertTrue(vagas["somente_leitura"][0].startswith("/"))  # no formato do WSL

    def test_linha_de_comando(self):
        r = rodar("registrar-projeto", "--raiz", self.raiz, "--projeto", "caso-real", "--origem", self.origem,
                  "--negar-skill", "squad-a")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = rodar("ler-projetos-host", "--raiz", self.raiz, "--projeto", "caso-real")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        dados = json.loads(r.stdout)
        self.assertTrue(dados["registrado"])
        self.assertEqual(dados["aninhadas_negadas"], ["squad-a"])
        r = rodar("ler-projetos-host", "--raiz", self.raiz, "--projeto", "lab-a")
        self.assertFalse(json.loads(r.stdout)["registrado"])
        r = rodar("registrar-projeto", "--raiz", self.raiz, "--projeto", "caso-real", "--origem", self.base / "nada")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_pasta_que_contem_a_raiz_nao_vai_ao_registro(self):
        """Revisão seguinte da terceira rodada da integração, defeito 1 (a lacuna vizinha): o registro recusava a pasta
        dentro da raiz, mas aceitava a que a contém; o Edit negado dela, que o perfil do Windows soma (I21), negaria às
        sessões a escrita na própria fundação. A mesma regra do Get-PastasConferidas dos scripts do Windows."""
        for valor in (self.base, self.base.parent, Path(self.raiz.anchor)):
            with self.subTest(valor=str(valor)):
                with self.assertRaises(ValueError) as erro:
                    self.m.registrar_projeto(self.raiz, "caso-real", [str(valor)])
                self.assertIn("contém a raiz", str(erro.exception))
                self.assertFalse(self.arquivo.exists())
        r = rodar("registrar-projeto", "--raiz", self.raiz, "--projeto", "caso-real", "--origem", self.origem,
                  "--somente-leitura", self.base)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("contém a raiz", r.stdout)
        self.assertFalse(self.arquivo.exists())
        self.m.registrar_projeto(self.raiz, "caso-real", [str(self.origem)])  # a vizinha, fora da raiz, segue valendo
        self.assertTrue(self.arquivo.is_file())


B = chr(92)  # a barra invertida dos caminhos do Windows nos dados de ensaio


class NegacoesForaDoRegistro(unittest.TestCase):
    """Revisão seguinte da terceira rodada da integração, defeito 3: o preparar-projeto.ps1 refaz o perfil do Windows só
    com o registro, e uma negação dada só na linha de comando do preparar-maquina.ps1 (-SomenteLeitura de pasta fora do
    registro, -NegarSkill de nome que nenhum projeto registrou) sumia em silêncio no próximo preparo. O ajudante
    (fora-do-registro) diz quais o registro não cobre; o script deixa a pendência com elas."""

    REGISTRO = {"schema_version": "fundacao.projetos_host/1", "projetos": {
        "lab-a": {"origens": ["/mnt/d/Origem Lab", "/home/ensaio/so-do-ubuntu"], "somente_leitura": ["C:" + B],
                  "aninhadas_negadas": ["squad-a"]},
        "caso-real": {"origens": ["E:" + B + "Origem Caso"], "somente_leitura": [], "aninhadas_negadas": ["squad-b"]}}}

    def test_o_que_o_registro_cobre_e_o_que_so_a_linha_de_comando_traz(self):
        m = carregar_preparo()
        fora = m.fora_do_registro(self.REGISTRO, [
            "D:" + B + "Origem Lab",  # a de /mnt/d, pela unidade e sem caixa
            "d:/origem lab/sub",  # dentro de uma registrada: o Edit negado dela já cobre
            "C:" + B + "Qualquer" + B + "Coisa",  # a raiz de um disco registrada cobre o disco
            "E:" + B + "Origem Caso",
            "E:" + B + "Origem Casos",  # o nome que só começa igual não é coberto
            "F:" + B + "Solta", "F:" + B + "Solta"], ["squad-a", "squad-b", "squad-solta", "squad-solta"])
        self.assertEqual(fora, {"somente_leitura": ["E:" + B + "Origem Casos", "F:" + B + "Solta"],
                                "negar_skill": ["squad-solta"], "negar_agente": []})
        vazio = {"schema_version": "fundacao.projetos_host/1", "projetos": {}}
        self.assertEqual(m.fora_do_registro(vazio, ["D:" + B + "x"], ["s"]),
                         {"somente_leitura": ["D:" + B + "x"], "negar_skill": ["s"], "negar_agente": []})

    def test_linha_de_comando(self):
        base = Path(tempfile.mkdtemp(prefix="fora-do-registro-1710-")).resolve()
        try:
            raiz = base / "Fundacao Ensaio"
            (raiz / "registry").mkdir(parents=True)
            (raiz / "registry" / "projetos-host.json").write_text(json.dumps(self.REGISTRO, ensure_ascii=False),
                                                                  encoding="utf-8", newline="\n")
            r = rodar("fora-do-registro", "--raiz", raiz, "--somente-leitura", "E:" + B + "Origem Caso",
                      "--somente-leitura", "G:" + B + "Nova", "--negar-skill", "squad-b", "--negar-skill", "squad-c")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(json.loads(r.stdout), {"somente_leitura": ["G:" + B + "Nova"], "negar_skill": ["squad-c"],
                                                  "negar_agente": []})
            (raiz / "registry" / "projetos-host.json").write_text('{"schema_version": "outro"}', encoding="utf-8")
            r = rodar("fora-do-registro", "--raiz", raiz, "--somente-leitura", "G:" + B + "Nova")
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)  # registro fora do esquema: nada sai
        finally:
            shutil.rmtree(base, ignore_errors=True)


class UltimaCopia(unittest.TestCase):
    """Revisão seguinte da terceira rodada da integração, defeito 2: o portão das cópias dos scripts do Windows lê
    registry/ultima-copia.json (fundacao.ultima_copia/1, que o backup criar do kit grava) pelo ajudante, como o hook
    aviso_copia.py o lê: sem seguir ligação nem vínculo físico, até 64 KiB, JSON estrito. O destino (na forma do Windows,
    com a pasta de cima) só recusa o -SemBackups e sugere a pasta no comando pronto, nunca aceita: uma sessão o forja.
    Por isso o destino com caractere que uma pasta do Windows não tem (as aspas quebrariam o argumento do comando pronto)
    ou com controle é recusado, e o motivo não traz conteúdo do arquivo."""

    def setUp(self):
        self.m = carregar_preparo()
        self.base = Path(tempfile.mkdtemp(prefix="ultima-copia-1710-")).resolve()
        self.raiz = self.base / "Fundacao Ensaio"
        (self.raiz / "registry").mkdir(parents=True)
        self.arquivo = self.raiz / "registry" / "ultima-copia.json"

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def gravar(self, destino, **extra) -> None:
        dados = {"schema_version": "fundacao.ultima_copia/1", "rotulo": "semanal-2026-S44",
                 "criada_em": "2026-10-30T10:00:00Z", "verificada_em": None, "destino": destino, **extra}
        self.arquivo.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    def test_ausente_e_lido(self):
        self.assertEqual(self.m.ultima_copia(self.raiz)["registro"], "ausente")
        casos = (("D:" + B + "Copias IA" + B + "semanal-2026-S44", "D:" + B + "Copias IA" + B + "semanal-2026-S44",
                  "D:" + B + "Copias IA"),
                 ("/mnt/e/Copias IA/semanal-2026-S44", "E:" + B + "Copias IA" + B + "semanal-2026-S44",
                  "E:" + B + "Copias IA"),  # a cópia feita pelo Ubuntu, no disco do Windows
                 ("F:/semanal-2026-S44/", "F:" + B + "semanal-2026-S44", "F:" + B),  # a pasta de cima é a raiz do disco
                 ("/home/ensaio/copias/semanal-2026-S44", None, None))  # só no Ubuntu: o perfil do Windows não alcança
        for destino, windows, pasta in casos:
            with self.subTest(destino=destino):
                self.gravar(destino)
                self.assertEqual(self.m.ultima_copia(self.raiz), {
                    "registro": "lido", "destino": destino, "destino_windows": windows, "pasta_das_copias": pasta,
                    "motivo": None})

    def test_recusas_sem_conteudo_do_arquivo_no_motivo(self):
        aspas = "E:" + B + 'Copias" -Python "C:' + B + "outro"
        casos = {"esquema": lambda: self.arquivo.write_text('{"schema_version": "outro", "destino": "D:/x"}',
                                                            encoding="utf-8"),
                 "chave repetida": lambda: self.arquivo.write_text(
                     '{"schema_version": "fundacao.ultima_copia/1", "destino": "D:/x", "destino": "D:/y"}',
                     encoding="utf-8"),
                 "constante": lambda: self.arquivo.write_text(
                     '{"schema_version": "fundacao.ultima_copia/1", "destino": "D:/x", "n": NaN}', encoding="utf-8"),
                 "acima do teto": lambda: self.gravar("D:/x", lixo="y" * (70 * 1024)),
                 "aninhado demais": lambda: self.arquivo.write_text("[" * 60000, encoding="utf-8"),
                 "aspas": lambda: self.gravar(aspas),
                 "controle": lambda: self.gravar("D:" + B + "a" + chr(0x202E) + "b"),
                 "longo": lambda: self.gravar("D:" + B + "x" * 500),
                 "relativo": lambda: self.gravar("copias/semanal"),
                 "rede": lambda: self.gravar(B + B + "servidor" + B + "copias"),
                 "sem destino": lambda: self.gravar(None)}
        for nome, preparar in casos.items():
            with self.subTest(nome):
                preparar()
                res = self.m.ultima_copia(self.raiz)
                self.assertEqual((res["registro"], res["destino"], res["pasta_das_copias"]), ("recusado", None, None))
                self.assertTrue(res["motivo"])
                self.assertNotIn("Python", res["motivo"])
                self.assertNotIn("servidor", res["motivo"])

    def test_ligacao_e_vinculo_fisico_sao_recusados(self):
        fora = self.base / "registro-fora"
        fora.mkdir()
        dados = {"schema_version": "fundacao.ultima_copia/1", "destino": "D:/Copias/semanal-2026-S44"}
        (fora / "ultima-copia.json").write_text(json.dumps(dados), encoding="utf-8")
        os.link(fora / "ultima-copia.json", self.arquivo)  # vínculo físico: o conteúdo pode ser de fora
        self.assertEqual(self.m.ultima_copia(self.raiz)["registro"], "recusado")
        self.arquivo.unlink()
        shutil.rmtree(self.raiz / "registry")
        criar_ligacao_dir(self.raiz / "registry", fora)  # registry/ ligada para fora da raiz
        res = self.m.ultima_copia(self.raiz)
        self.assertEqual(res["registro"], "recusado")
        self.assertIn("ligação", res["motivo"])

    def test_linha_de_comando(self):
        self.gravar("D:" + B + "Copias IA" + B + "semanal-2026-S44")
        r = rodar("ultima-copia", "--raiz", self.raiz)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["pasta_das_copias"], "D:" + B + "Copias IA")


if __name__ == "__main__":
    unittest.main()
