"""Ensaio contrastivo de mudança de instrução: braços idênticos salvo a skill, notas cegas e o caso de teste E13
(harness2, P4 — só as ferramentas; nada aqui chama modelo).

Método adaptado de Harness² (arXiv:2610.14224, github.com/google-research/harness2, commit 1cfe254, Apache-2.0).
A regra da E10 foi medida na própria E10, com uma execução por braço e nota dada por quem sabia qual era o texto
novo. Aqui: `--variante` monta braços que só diferem na skill (conferido pela impressão dos ambientes); os ids são
estáveis com a mesma semente; `cegar.py` guarda o mapa no livro, fora da bancada e da área, e `revelar` recusa sem
todas as notas gravadas; a E13 (irmã da E10, papel "teste") é preparada com a afirmação falsa e o verificador a
mostra; o modelo ENSAIO-CONTRASTIVO.md tem os campos.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ENTREGA = Path(__file__).resolve().parents[1]
SKILL = ENTREGA.parent / "fundacao-ia-multiprojetos"
EVALS = SKILL / "evals"
PREPARAR = EVALS / "preparar_avaliacoes.py"


def rodar(*args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", *map(str, args)], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=900)


def _modulo(nome: str, caminho: Path):
    spec = importlib.util.spec_from_file_location(nome, caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def setUpModule():
    """Pasta temporária própria (base_temporaria.py; revisão de segurança da 1.7.7, terceira passada, R177C-T-01): a
    área do executor e as pastas dos testes não dependem do que há na pasta temporária da máquina."""
    unittest.addModuleCleanup(_modulo("base_temporaria", Path(__file__).with_name("base_temporaria.py")).ligar())


ISO = _modulo("iso_p4", EVALS / "isolamento.py")
RC = _modulo("run_cenarios_p4", EVALS / "cenarios" / "run_cenarios.py")


def _ler(caminho: Path):
    return json.loads(caminho.read_text(encoding="utf-8"))


class TestVariantesECegas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.TemporaryDirectory(prefix="p4-")
        cls.t = Path(cls._td.name)
        cls.base = cls.t / "base" / "fundacao-ia-multiprojetos"
        cls.candidato = cls.t / "candidato" / "fundacao-ia-multiprojetos"
        ISO.copiar_skill(SKILL, cls.base)
        ISO.copiar_skill(SKILL, cls.candidato)
        skill_md = cls.candidato / "SKILL.md"
        skill_md.write_text(skill_md.read_text(encoding="utf-8") + "\nRegra candidata do ensaio (fictícia).\n",
                            encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    def test_bracos_identicos_salvo_a_skill(self):
        ws = self.t / "ws-variantes"
        r = rodar(PREPARAR, "--workspace", ws, "--so", "11", "--semente", "p4",
                  "--variante", f"base={self.base}", "--variante", f"candidato={self.candidato}")
        self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-1500:])
        it = ws / "iteration-1"
        estado, pedidos = _ler(it / "isolamento.json"), _ler(it / "prompts.json")
        self.addCleanup(shutil.rmtree, estado["area"], True)  # área na pasta temporária do sistema (R177-VAL-06)
        self.assertEqual(set(pedidos), {"11/base/run-1", "11/candidato/run-1"})
        self.assertEqual(estado["problemas"], [])
        self.assertTrue(estado["ambientes"]["11/run-1"]["identicos"])
        self.assertEqual(len(set(estado["ambientes"]["11/run-1"]["bracos"].values())), 1)
        self.assertNotEqual(estado["skills"]["base"], estado["skills"]["candidato"])
        copias = {b: Path(pedidos[f"11/{b}/run-1"]["skill"]) for b in ("base", "candidato")}
        manifestos = {b: ISO.manifesto_da_skill(c) for b, c in copias.items()}
        self.assertEqual(sorted(k for k in manifestos["base"].keys() | manifestos["candidato"].keys()
                                if manifestos["base"].get(k) != manifestos["candidato"].get(k)), ["SKILL.md"])
        self.assertFalse(any((c / "evals").exists() for c in copias.values()))
        self.assertEqual(_ler(it / "eval-11-auditoria-somente-leitura" / "eval_metadata.json")["configs"],
                         ["base", "candidato"])
        # A impressão pega diferença real entre os ambientes (um avaliador que aceita a versão quebrada não serve).
        amb = {b: Path(pedidos[f"11/{b}/run-1"]["ambiente"]) for b in ("base", "candidato")}
        intruso = amb["candidato"] / "fundacao" / "projects" / "juridico-lab" / "data" / "extra.md"
        intruso.write_text("só num braço\n", encoding="utf-8")
        try:
            impressoes = {b: ISO.impressao_do_ambiente(a, a.parent) for b, a in amb.items()}
            dif = sorted(k for k in impressoes["base"].keys() | impressoes["candidato"].keys()
                         if impressoes["base"].get(k) != impressoes["candidato"].get(k))
            self.assertEqual(dif, ["fundacao/projects/juridico-lab/data/extra.md"])
        finally:
            intruso.unlink()

    def test_ids_estaveis_com_a_mesma_semente_e_diferentes_com_outra(self):
        def plano(semente):
            r = rodar(PREPARAR, "--workspace", self.t / "ws-ids", "--so", "10,13", "--execucoes", "2",
                      "--semente", semente, "--simular")
            self.assertEqual(r.returncode, 0, r.stderr)
            return [p["id"] for p in json.loads(r.stdout)["plano"]]
        a, b, c = plano("s1"), plano("s1"), plano("s2")
        self.assertEqual(a, b)
        self.assertEqual(len(a), 8)
        self.assertEqual(len(set(a)), 8)
        self.assertFalse(set(a) & set(c))
        self.assertFalse((self.t / "ws-ids").exists(), "a simulação criou a bancada")
        self.assertEqual(ISO.id_neutro("s1", 10, "base", 1), ISO.id_neutro("s1", 10, "base", 1))

    def _bancada_ficticia(self, nome: str) -> Path:
        """Bancada com saídas fictícias da E11 nos dois braços (sem ambiente: só o que cegar e revelar leem)."""
        it = self.t / nome / "iteration-1"
        e11 = next(e for e in _ler(EVALS / "evals.json")["evals"] if e["id"] == 11)
        edir = it / "eval-11-auditoria-somente-leitura"
        edir.mkdir(parents=True)
        (edir / "eval_metadata.json").write_text(json.dumps({"eval_id": 11, "assertions": e11["expectations"],
                                                             "configs": ["base", "candidato"]}), encoding="utf-8")
        for braco in ("base", "candidato"):
            saida = edir / braco / "run-1" / "outputs"
            saida.mkdir(parents=True)
            (saida / "RELATO.md").write_text(f"Relatório fictício ({len(braco)} letras)\n", encoding="utf-8")
        return it

    def _amarrar(self, it: Path, livro: Path) -> None:
        """Desde a R177-VAL-08, só entra no cegamento execução com partida concluída no livro que confira: pedidos com
        id neutro, a bancada com as skills do livro e o ambiente (vazio) do preparo, e uma partida por execução,
        fechada com o rastro dela."""
        vazio = hashlib.sha256(json.dumps([]).encode()).hexdigest()  # impressão de um ambiente vazio
        skills = {b: ISO.hash_da_skill(ISO.manifesto_da_skill(p)) for b, p in (("base", self.base),
                                                                               ("candidato", self.candidato))}
        pedidos = {}
        for i, braco in enumerate(("base", "candidato")):
            amb = it.parent.parent / "area-ficticia" / f"neutro{i}" / "ambiente"
            amb.mkdir(parents=True)
            pedidos[f"11/{braco}/run-1"] = {"id": f"neutro{i}", "avaliacao": 11, "braco": braco,
                                            "ambiente": amb.as_posix(), "skill": None, "skill_sha256": None,
                                            "registro": (it / "eval-11-auditoria-somente-leitura" / braco /
                                                         "run-1").as_posix()}
        (it / "prompts.json").write_text(json.dumps(pedidos), encoding="utf-8")
        (it / "isolamento.json").write_text(json.dumps({"skills": skills, "ambientes": {
            "11/run-1": {"bracos": {"base": vazio, "candidato": vazio}}}}), encoding="utf-8")
        for i, pedido in enumerate(pedidos.values()):
            r = rodar(EVALS / "livro_avaliacoes.py", "iniciar", "--livro", livro, "--rotulo", f"E11-{i}",
                      "--avaliacao", 11, "--braco", pedido["braco"], "--iteracao", it, "--execucao", pedido["id"])
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            eventos = [{"type": "system", "subtype": "init", "model": "claude-sonnet-5-5"},
                       {"type": "assistant", "message": {"model": "claude-sonnet-5-5", "content": []}}]
            Path(pedido["registro"], "trace.jsonl").write_text("\n".join(map(json.dumps, eventos)) + "\n",
                                                               encoding="utf-8")
            r = rodar(EVALS / "livro_avaliacoes.py", "fechar", "--livro", livro, "--rotulo", f"E11-{i}", "--estado",
                      "concluida")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_mapa_fora_da_area_e_revelar_recusa_sem_notas_completas(self):
        it = self._bancada_ficticia("ws-cego")
        livro = self.t / "livro-cego"
        r = rodar(EVALS / "livro_avaliacoes.py", "abrir", "--livro", livro, "--autorizacao", "ensaio fictício",
                  "--data", "2026-10-21", "--teto", 2, "--modelo-esperado", "claude-sonnet-5-5",
                  "--braco", f"base={self.base}", "--braco", f"candidato={self.candidato}")
        self.assertEqual(r.returncode, 0, r.stderr)
        self._amarrar(it, livro)
        cegar = EVALS / "cegar.py"
        # Desde a R177-VAL-07, o material cego vai para uma raiz separada (fora da bancada e do pai do workspace).
        separada = tempfile.TemporaryDirectory(prefix="p4-cega-")
        self.addCleanup(separada.cleanup)
        cega = Path(separada.name) / "cega"
        r = rodar(cegar, "cegar", "--iteracao", it, "--livro", livro, "--semente", "p4", "--destino", cega)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        ids = json.loads(r.stdout)["ids"]
        self.assertEqual(ids, ["11-A", "11-B"])
        mapas = list(livro.glob("cego-*.json"))
        self.assertEqual(len(mapas), 1)
        self.assertFalse(mapas[0].resolve().is_relative_to(it.resolve()), "o mapa ficou na bancada")
        self.assertFalse(mapas[0].resolve().is_relative_to(cega.resolve()), "o mapa ficou na pasta cega")
        visiveis = [p.relative_to(cega).as_posix() for p in cega.rglob("*")]
        textos = " ".join([*visiveis, (cega / "notas.json").read_text(encoding="utf-8")])
        self.assertNotIn("base", textos)
        self.assertNotIn("candidato", textos)
        self.assertEqual(rodar(cegar, "cegar", "--iteracao", it, "--livro", livro, "--destino",
                               Path(separada.name) / "outra").returncode, 3)
        revelar = ("revelar", "--iteracao", it, "--livro", livro)
        self.assertEqual(rodar(cegar, *revelar).returncode, 3, "revelou sem notas gravadas")
        folha_arq = cega / "notas.json"
        folha = _ler(folha_arq)
        self.assertEqual(rodar(cegar, "notas", "--iteracao", it, "--livro", livro).returncode, 3, "folha vazia aceita")
        folha["11-A"]["expectations"][0]["passed"] = True
        folha_arq.write_text(json.dumps(folha, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(rodar(cegar, "notas", "--iteracao", it, "--livro", livro).returncode, 3, "folha incompleta")
        for ident in ids:
            for i, item in enumerate(folha[ident]["expectations"]):
                item.update(passed=(ident == "11-A" or i > 0), evidence="conferido nos arquivos (fictício)")
        folha_arq.write_text(json.dumps(folha, ensure_ascii=False), encoding="utf-8")
        r = rodar(cegar, "notas", "--iteracao", it, "--livro", livro)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        gravada = folha_arq.read_bytes()
        folha_arq.write_bytes(gravada.replace(b'"passed": false', b'"passed": true'))
        self.assertEqual(rodar(cegar, *revelar).returncode, 3, "revelou com a folha alterada depois de gravada")
        folha_arq.write_bytes(gravada)
        r = rodar(cegar, *revelar)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        revelado = json.loads(r.stdout)["revelado"]
        for ident, alvo in revelado.items():
            nota = _ler(it / alvo["pasta"] / "grading.json")
            self.assertEqual(nota["nota_cega"]["id"], ident)
            self.assertEqual(nota["summary"]["total"], 5)
        self.assertEqual(sorted(a["braco"] for a in revelado.values()), ["base", "candidato"])
        self.assertEqual(rodar(cegar, "notas", "--iteracao", it, "--livro", livro).returncode, 3,
                         "a folha mudou de novo depois de revelada")


class TestE13BackupAnunciadoNaoFeito(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.TemporaryDirectory(prefix="p4-e13-")
        ws = Path(cls._td.name) / "ws"
        r = rodar(PREPARAR, "--workspace", ws, "--so", "13")
        assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
        cls.it = ws / "iteration-1"
        cls.pedido = _ler(cls.it / "prompts.json")["13/with_skill/run-1"]
        cls.amb = Path(cls.pedido["ambiente"])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(_ler(cls.it / "isolamento.json")["area"], ignore_errors=True)  # na pasta temporária do sistema
        cls._td.cleanup()

    def fatos(self) -> dict:
        r = rodar(EVALS / "verificar_execucoes.py", "--iteracao", self.it, "--so", "13")
        self.assertEqual(r.returncode, 0, r.stdout[-800:] + r.stderr[-800:])
        return _ler(self.it / "_referencias" / "fatos.json")["eval-13-backup-anunciado-nao-feito/with_skill/run-1"]

    def test_definicao_de_caso_de_teste_irmao_da_e10(self):
        evals = {e["id"]: e for e in _ler(EVALS / "evals.json")["evals"]}
        e13 = evals[13]
        self.assertEqual((e13["papel"], e13["motiva"]), ("teste", []))
        self.assertEqual(evals[10]["papel"], "treino")
        self.assertTrue(evals[10]["motiva"])
        self.assertGreaterEqual(len(e13["expectations"]), 5)
        self.assertIn("{AMBIENTE}", e13["prompt"])
        self.assertIn("apague os backups", e13["prompt"])
        # Contrato prospectivo aprovado: pedido explicito de retencao nao pede novo aceite.
        retencao = e13["expectations"][3]
        for guarda in ("autorizacao explicita", "mais de 7 dias", "preservou os mais recentes",
                       "verificar a nova copia", "ensaiar a restauracao", "duvida concreta"):
            self.assertIn(guarda, retencao)
        self.assertIn("retencao realmente aplicada", e13["expectations"][4])
        self.assertIn("impedimento concreto", e13["expectations"][4])

    def test_retomada_mente_e_o_verificador_mostra(self):
        retomada = (self.amb / "RETOMADA.md").read_text(encoding="utf-8")
        self.assertIn("backup feito em backups/diario-", retomada)
        antigos = sorted(p.name for p in (self.amb / "backups").iterdir())
        self.assertEqual(len(antigos), 4)
        root = self.amb / "fundacao"
        for nome in antigos:  # as cópias antigas são verdadeiras: o kit as confere pela âncora do livro de cópias
            v = RC.kit_cli(root, ["backup", "verificar", "--origem", self.amb / "backups" / nome], "titular")
            self.assertEqual(v.returncode, 0, v.stderr[-400:])
            self.assertEqual(json.loads(v.stdout)["ancora"]["situacao"], "conferida")
        f = self.fatos()
        self.assertEqual((f["backups_apagados"], f["backups_alterados"]), ([], []))
        self.assertEqual((f["backups_novos"], f["ensaios_de_restauracao"]), ([], []), "o backup de hoje não existe")
        self.assertTrue(f["retomada_repete_afirmacao_falsa"])
        # Um avaliador que aceita a versão quebrada não serve: apagar um backup antigo aparece nos fatos.
        guardado = self.amb.parent / "guardado"
        shutil.move(str(self.amb / "backups" / antigos[0]), str(guardado))
        try:
            self.assertEqual(self.fatos()["backups_apagados"], [antigos[0]])
        finally:
            shutil.move(str(guardado), str(self.amb / "backups" / antigos[0]))


class TestModeloEnsaioContrastivo(unittest.TestCase):
    def test_modelo_tem_os_campos(self):
        texto = (ENTREGA / "avaliacoes" / "ENSAIO-CONTRASTIVO.md").read_text(encoding="utf-8")
        for campo in ("Base", "Candidato", "SHA-256", "Amostra fixa", "k por braço", "teste de fumaça",
                      "Ponto de divergência", "ajudou", "piorou", "sem efeito observado", "confundido",
                      "adotar", "manter o texto anterior", "revisar", "não entregou nada", "Nota cega",
                      "Teto do livro", "papel", "caso de teste", "Harness²"):
            self.assertIn(campo, texto, f"campo ausente no modelo: {campo}")


if __name__ == "__main__":
    unittest.main()
