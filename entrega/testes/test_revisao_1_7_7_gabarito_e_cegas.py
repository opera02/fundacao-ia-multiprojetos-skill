"""Revisão de segurança da 1.7.7 nas avaliações: isolamento do gabarito (R177-VAL-06) e material cego fora da bancada
(R177-VAL-07).

R177-VAL-06 — três furos. (1) A área padrão do executor era a pasta-mãe do workspace: com o workspace no padrão do
skill-creator, `--simular` punha a área em `<repo>/trabalho-…`, ao lado de `fundacao-ia-multiprojetos/evals/`;
agora fica fora do repositório e do pai do workspace, e as pastas acima dela são conferidas. (2) O alarme só
conferia uma raiz dentro da outra. (3) O detector do rastro comparava nomes exatos e prefixos: curinga que alcançava
a bancada ou `evals/` e a leitura da cópia da skill de outra execução saíam "sem acesso"; e o nome do repositório era
testado antes de excluir os caminhos da própria execução (numa árvore chamada `fundacao-ia-multiprojetos-skill`,
ler o próprio ambiente saía "contaminada").
Nada aqui chama modelo, `claude`, `codex` nem rede.
"""

from __future__ import annotations

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
VERIFICADOR = EVALS / "verificar_execucoes.py"


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


def _trace(pasta: Path, *usos) -> Path:
    linhas = [{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"u{i}", "name": nome,
                                                             "input": entrada}]}}
              for i, (nome, entrada) in enumerate(usos)]
    pasta.mkdir(parents=True, exist_ok=True)
    trace = pasta / "trace.jsonl"
    trace.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in linhas) + "\n", encoding="utf-8")
    return trace


class TestR177Val06AreaForaDoRepositorio(unittest.TestCase):
    def test_area_padrao_fica_fora_do_repositorio_e_do_pai_do_workspace(self):
        """O caso do achado: workspace no padrão do skill-creator, ao lado da skill (nada é criado na simulação)."""
        ws = SKILL.parent / "fundacao-ia-multiprojetos-workspace"
        r = rodar(PREPARAR, "--workspace", ws, "--iteracao", "977", "--so", "10", "--simular")
        self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-1500:])
        area = Path(json.loads(r.stdout)["area"]).resolve()
        for perto in (SKILL.parent.resolve(), ws.resolve().parent, ws.resolve()):
            self.assertFalse(area.is_relative_to(perto), f"área do executor em {area}, dentro de {perto}")
        self.assertFalse((ws / "iteration-977").exists(), "a simulação criou a bancada")

    def test_area_perto_do_gabarito_e_recusada_antes_de_criar_qualquer_coisa(self):
        with tempfile.TemporaryDirectory(prefix="r177-06-") as td:
            t = Path(td)
            ws = t / "repo" / "fundacao-ia-multiprojetos-workspace"
            vizinho = t / "outro" / "fundacao-ia-multiprojetos-workspace"  # um workspace ao lado da pasta acima
            vizinho.mkdir(parents=True)
            for area in (t / "repo" / "trabalho-perto", t / "outro" / "area"):
                with self.subTest(area=area.relative_to(t).as_posix()):
                    r = rodar(PREPARAR, "--workspace", ws, "--so", "1", "--area", area, "--simular")
                    self.assertEqual(r.returncode, 3, r.stdout[-800:] + r.stderr[-800:])
                    self.assertIn("área do executor", json.loads(r.stdout)["recusaria"])
                    r = rodar(PREPARAR, "--workspace", ws, "--so", "1", "--area", area)
                    self.assertEqual(r.returncode, 3, r.stdout[-800:] + r.stderr[-800:])
                    self.assertFalse(ws.exists() or area.exists(), "a recusa criou a bancada ou a área")


class TestR177Val06DetectorDoRastro(unittest.TestCase):
    """Acesso ao gabarito pela estrutura do rastro: curinga, outra execução, `cd` e os caminhos próprios."""

    @classmethod
    def setUpClass(cls):
        cls.ve = _modulo("ve_r177_06", VERIFICADOR)

    def _estado(self, *usos, raiz_nome: str = "t") -> dict:
        with tempfile.TemporaryDirectory(prefix="r177-06-rastro-") as td:
            t = Path(td).resolve() / raiz_nome  # os pedidos levam caminhos resolvidos (sem nome 8.3 do Windows)
            it = t / "ws" / "iteration-1"
            (it / "eval-10-retomada-desatualizada" / "with_skill" / "run-1").mkdir(parents=True)
            area = t / "trabalho-x"
            execucao, outra = area / "a1b2c3d4e5", area / "f6e7d8c9b0"
            for pasta in (execucao, outra):
                for sub in ("ambiente", "saidas", "skill/fundacao-ia-multiprojetos"):
                    (pasta / sub).mkdir(parents=True)
            dev = t / "repo" / "fundacao-ia-multiprojetos"  # árvore de desenvolvimento, com o gabarito em evals/
            (dev / "evals").mkdir(parents=True)
            (dev / "evals" / "evals.json").write_text("{}", encoding="utf-8")
            trocas = {"<BANCADA>": it.as_posix(), "<WS>": it.parent.as_posix(),
                      "<AMB>": (execucao / "ambiente").as_posix(),
                      "<SAIDAS>": (execucao / "saidas").as_posix(), "<EXEC>": execucao.as_posix(),
                      "<OUTRA>": outra.as_posix(), "<AREA>": area.as_posix(), "<DEV>": dev.as_posix(),
                      "<RAIZ>": t.as_posix()}
            reais = []
            for nome, entrada in usos:
                texto = json.dumps(entrada)
                for marca, valor in trocas.items():
                    texto = texto.replace(marca, valor)
                reais.append((nome, json.loads(texto)))
            return self.ve.acesso_ao_gabarito(_trace(t / "rastro", *reais), it, self.ve.nomes_do_gabarito(it),
                                              (execucao / "ambiente", execucao / "saidas", execucao), area=area,
                                              protegidas=(dev,))

    def test_curinga_outra_execucao_e_cd_contaminam(self):
        casos = [
            ("Glob", {"pattern": "<WS>/*/*/*.json"}),                       # curinga que alcança a bancada
            ("Bash", {"command": "ls <WS>/iter*"}),                          # curinga que designa a bancada
            ("Glob", {"path": "<WS>", "pattern": "*/*/*.json"}),             # pasta e padrão juntos
            ("Bash", {"command": "cat <DEV>/ev*/*.json"}),                   # curinga em evals/ da árvore da skill
            ("Read", {"file_path": "<DEV>/SKILL.md"}),                       # a skill da árvore com evals/
            ("Read", {"file_path": "<OUTRA>/skill/fundacao-ia-multiprojetos/SKILL.md"}),  # cópia de outra execução
            ("Bash", {"command": "cat ../../f6e7d8c9b0/saidas/RELATO.md"}),  # saídas do outro braço, por relativo
            ("Bash", {"command": "ls ../../*/skill"}),                       # curinga a partir da área
            ("Bash", {"command": "find ../.. -name SKILL.md"}),              # busca recursiva a partir da área
            ("Bash", {"command": "ls ../../../*"}),                          # curinga acima da área
            ("Bash", {"command": "cd <WS> && cat */*/*.json"}),             # cd e curinga relativo
            ("PowerShell", {"command": "Set-Location <WS>; Get-Content iter*\\eval-*\\*.json"}),
        ]
        for uso in casos:
            with self.subTest(uso):
                r = self._estado(uso)
                self.assertEqual(r["estado"], "contaminada", r)

    def test_trabalho_na_propria_execucao_nao_conta(self):
        for uso in (("Bash", {"command": "cat <AMB>/RETOMADA.md"}),
                    ("Bash", {"command": "ls -la .."}),
                    ("Read", {"file_path": "<EXEC>/skill/fundacao-ia-multiprojetos/SKILL.md"}),
                    ("Glob", {"pattern": "**/*.md", "path": "<AMB>"}),
                    ("Bash", {"command": "cd <AMB>/fundacao && python -m fundacao --raiz . status && ls .."}),
                    ("Bash", {"command": "ls *.json && cat ../saidas/RELATO.md"}),
                    ("Write", {"file_path": "<SAIDAS>/RELATO.md", "content": "evals.json e with_skill no texto"})):
            with self.subTest(uso):
                r = self._estado(uso)
                self.assertEqual((r["estado"], r["usos"]), ("sem_acesso_no_rastro", []), r)

    def test_caminhos_proprios_saem_antes_do_teste_de_nome(self):
        """Bancada e área numa árvore chamada como o repositório: ler o próprio ambiente não contamina; ler o resto
        da árvore, sim."""
        raiz = "fundacao-ia-multiprojetos-skill"
        limpo = self._estado(("Bash", {"command": "cat <AMB>/RETOMADA.md"}),
                             ("Read", {"file_path": "<EXEC>/skill/fundacao-ia-multiprojetos/SKILL.md"}), raiz_nome=raiz)
        self.assertEqual((limpo["estado"], limpo["usos"]), ("sem_acesso_no_rastro", []), limpo)
        sujo = self._estado(("Read", {"file_path": "<RAIZ>/LEIA-ME.md"}), raiz_nome=raiz)
        self.assertEqual(sujo["estado"], "contaminada", sujo)


class TestR177Val06VerificadorUsaAreaEGabarito(unittest.TestCase):
    """Pelo verificador inteiro: o braço sem a skill que lê a cópia do outro braço ou a árvore da skill é
    contaminado."""

    def test_leitura_da_skill_de_outra_execucao_ou_da_arvore_contamina(self):
        with tempfile.TemporaryDirectory(prefix="r177-06-ve-") as td:
            ws = Path(td) / "ws"
            it = ws / "iteration-1"
            try:
                r = rodar(PREPARAR, "--workspace", ws, "--so", "1")
                self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-1500:])
                pedidos = json.loads((it / "prompts.json").read_text(encoding="utf-8"))
                copia = Path(pedidos["1/with_skill/run-1"]["skill"])
                sem = Path(pedidos["1/without_skill/run-1"]["registro"])
                for uso, esperado in ((("Read", {"file_path": (copia / "SKILL.md").as_posix()}), "contaminada"),
                                      (("Read", {"file_path": (SKILL / "SKILL.md").as_posix()}), "contaminada"),
                                      (("Bash", {"command": f"cat {pedidos['1/without_skill/run-1']['ambiente']}/x"}),
                                       "sem_acesso_no_rastro")):
                    with self.subTest(uso):
                        _trace(sem, uso)
                        r = rodar(VERIFICADOR, "--iteracao", it, "--so", "1")
                        self.assertEqual(r.returncode, 0, r.stdout[-800:] + r.stderr[-800:])
                        fatos = json.loads((it / "_referencias" / "fatos.json").read_text(encoding="utf-8"))
                        acesso = fatos["eval-1-nova-fundacao/without_skill/run-1"]["acesso_ao_gabarito"]
                        self.assertEqual(acesso["estado"], esperado, acesso)
            finally:
                apagar_area(it)


def apagar_area(it: Path) -> None:
    """A área do executor padrão fica na pasta temporária do sistema, fora da pasta do teste: apaga ao terminar."""
    estado = it / "isolamento.json"
    if estado.is_file():
        shutil.rmtree(json.loads(estado.read_text(encoding="utf-8"))["area"], ignore_errors=True)


def _sha(caminho: Path) -> str:
    import hashlib
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def amarrar(edir: Path, livro: Path, execucoes: list[tuple[str, int]], skills: dict[str, str],
            modelo: str = "claude-sonnet-5-5") -> None:
    """Desde a R177-VAL-08, só entra no cegamento execução com partida concluída no livro que confira. Para execuções
    fictícias de `edir`: pedidos com id neutro, `isolamento.json` com as skills do livro (`skills`: braço -> hash) e
    ambiente vazio, e uma partida amarrada a cada uma, fechada com o rastro da própria execução."""
    import hashlib
    it, eid = edir.parent, json.loads((edir / "eval_metadata.json").read_text(encoding="utf-8"))["eval_id"]
    vazio = hashlib.sha256(json.dumps([]).encode()).hexdigest()  # impressão de um ambiente vazio
    pedidos, estado = {}, {"skills": skills, "ambientes": {}}
    for braco, k in execucoes:
        ident = hashlib.sha256(f"{eid}|{braco}|{k}".encode()).hexdigest()[:10]
        amb = it.parent.parent / "area-ficticia" / ident / "ambiente"
        amb.mkdir(parents=True)
        pedidos[f"{eid}/{braco}/run-{k}"] = {"id": ident, "avaliacao": eid, "braco": braco, "ambiente": amb.as_posix(),
                                             "skill": None, "skill_sha256": None,
                                             "registro": (edir / braco / f"run-{k}").as_posix()}
        estado["ambientes"].setdefault(f"{eid}/run-{k}", {"bracos": {}})["bracos"][braco] = vazio
    (it / "prompts.json").write_text(json.dumps(pedidos), encoding="utf-8")
    (it / "isolamento.json").write_text(json.dumps(estado), encoding="utf-8")
    for i, pedido in enumerate(pedidos.values()):
        r = rodar(EVALS / "livro_avaliacoes.py", "iniciar", "--livro", livro, "--rotulo", f"E{eid}-{i}", "--avaliacao",
                  eid, "--braco", pedido["braco"], "--iteracao", it, "--execucao", pedido["id"])
        assert r.returncode == 0, r.stdout + r.stderr
        eventos = [{"type": "system", "subtype": "init", "model": modelo},
                   {"type": "assistant", "message": {"model": modelo, "content": [{"type": "text", "text": "ok"}]}},
                   {"type": "result", "subtype": "success", "is_error": False}]
        Path(pedido["registro"], "trace.jsonl").write_text("\n".join(map(json.dumps, eventos)) + "\n", encoding="utf-8")
        r = rodar(EVALS / "livro_avaliacoes.py", "fechar", "--livro", livro, "--rotulo", f"E{eid}-{i}", "--estado",
                  "concluida")  # sem --transcricao: o rastro da execução amarrada
        assert r.returncode == 0, r.stdout + r.stderr


class TestR177Val07MaterialCegoForaDaBancada(unittest.TestCase):
    """Na 1.7.7, `cegar` copiava as saídas byte a byte para `<bancada>/cego/`, ao lado dos originais em
    `eval-*/<braço>/run-*/outputs` e do prompts.json, e o procedimento mandava dar as notas na bancada: o SHA-256
    recuperava o mapa (3 de 3). Agora o material cego vai para uma raiz separada, entregue sozinha a quem dá as
    notas."""

    def setUp(self):
        td = tempfile.TemporaryDirectory(prefix="r177-07-")
        self.addCleanup(td.cleanup)
        self.t = Path(td.name).resolve()
        self.it = self.t / "repo" / "ws" / "iteration-1"  # workspace com pai próprio: a pasta cega fica fora dele
        e11 = next(e for e in json.loads((EVALS / "evals.json").read_text(encoding="utf-8"))["evals"] if e["id"] == 11)
        edir = self.it / "eval-11-auditoria-somente-leitura"
        edir.mkdir(parents=True)
        (edir / "eval_metadata.json").write_text(json.dumps({"eval_id": 11, "assertions": e11["expectations"],
                                                             "configs": ["base", "candidato"]}), encoding="utf-8")
        for k, braco in enumerate(("base", "candidato", "base")):  # base/run-1, candidato/run-1, base/run-2
            saida = edir / braco / f"run-{1 + k // 2}" / "outputs"
            saida.mkdir(parents=True, exist_ok=True)
            (saida / "RELATO.md").write_text(f"Relatório fictício número {k}\n", encoding="utf-8")
        self.livro = self.t / "livros" / "l1"
        r = rodar(EVALS / "livro_avaliacoes.py", "abrir", "--livro", self.livro, "--autorizacao", "ensaio fictício",
                  "--data", "2026-10-21", "--teto", 3, "--modelo-esperado", "claude-sonnet-5-5",
                  "--braco", "base=", "--braco", "candidato=")
        self.assertEqual(r.returncode, 0, r.stderr)
        amarrar(edir, self.livro, [("base", 1), ("candidato", 1), ("base", 2)],
                {"base": "sem_skill", "candidato": "sem_skill"})

    def cegar(self, *extra) -> subprocess.CompletedProcess:
        return rodar(EVALS / "cegar.py", "cegar", "--iteracao", self.it, "--livro", self.livro, "--semente", "r177",
                     *extra)

    def test_material_cego_numa_raiz_separada_sem_como_deduzir_o_mapa(self):
        cega = self.t / "entregar" / "notas-cegas"
        r = self.cegar("--destino", cega)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((self.it / "cego").exists(), "material cego dentro da bancada")
        self.assertEqual(Path(json.loads(r.stdout)["folha"]), cega / "notas.json")
        # O ataque do achado, só com o que quem dá as notas recebe: nenhuma cópia de uma saída fora das pastas cegas,
        # nenhum nome de braço, de caso nem caminho da bancada.
        cegas = {_sha(p): p for p in cega.rglob("*") if p.is_file() and "saidas" in p.parts}
        self.assertEqual(len(cegas), 3)
        for p in cega.rglob("*"):
            rel = p.relative_to(cega).as_posix()
            self.assertNotRegex(rel, r"base|candidato|eval-|run-")
            if p.is_file():
                texto = p.read_text(encoding="utf-8")
                for marca in ("candidato", "auditoria-somente-leitura", self.it.as_posix(), str(self.it)):
                    self.assertNotIn(marca, texto, rel)
                self.assertTrue(_sha(p) not in cegas or cegas[_sha(p)] == p,
                                f"cópia de saída fora da pasta cega: {rel}")

    def test_pasta_cega_na_bancada_perto_dela_ou_sem_destino_e_recusada(self):
        self.assertEqual(self.cegar().returncode, 2, "cegou sem pasta cega separada")
        ws = self.it.parent
        for destino in (self.it / "cego", ws / "cego", ws.parent / "cego", self.livro / "cego",
                        self.livro.parent / "cego"):
            with self.subTest(destino=destino.relative_to(self.t).as_posix()):
                antes = (self.livro / "livro.json").read_bytes()
                r = self.cegar("--destino", destino)
                self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
                self.assertFalse(destino.exists(), "a recusa criou a pasta cega")
                self.assertEqual((self.livro / "livro.json").read_bytes(), antes, "a recusa gravou no livro")

    def test_notas_e_revelacao_pela_pasta_cega(self):
        cega = self.t / "entregar" / "notas-cegas"
        self.assertEqual(self.cegar("--destino", cega).returncode, 0)
        folha = json.loads((cega / "notas.json").read_text(encoding="utf-8"))
        for item in (i for nota in folha.values() for i in nota["expectations"]):
            item.update(passed=True, evidence="conferido nos arquivos (fictício)")
        (cega / "notas.json").write_text(json.dumps(folha, ensure_ascii=False), encoding="utf-8")
        for acao in ("notas", "revelar"):
            r = rodar(EVALS / "cegar.py", acao, "--iteracao", self.it, "--livro", self.livro)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        notas = sorted(self.it.rglob("grading.json"))
        self.assertEqual(len(notas), 3)
        self.assertTrue((cega / "revelado.json").is_file())
        # R177-VAL-08: a nota revelada leva o livro; o resumo, mesmo sem --livro, não conta execução sem partida.
        intrusa = self.it / "eval-11-auditoria-somente-leitura" / "base" / "run-3"
        shutil.copytree(notas[0].parent, intrusa)
        r = rodar(EVALS / "resumo_k.py", "--iteracao", self.it)
        self.assertEqual(r.returncode, 0, r.stdout[-800:] + r.stderr[-800:])
        resumo = json.loads(r.stdout)
        execucoes = resumo["avaliacoes"]["eval-11-auditoria-somente-leitura"]["bracos"]["base"]["execucoes"]
        self.assertEqual({k: v["estado"] for k, v in execucoes.items()},
                         {"run-1": "aprovada", "run-2": "aprovada", "run-3": "nao_medida"}, execucoes)
        self.assertIn(str(self.livro), resumo["livro"])


class TestR177Val07TextoDoEnsaio(unittest.TestCase):
    def test_procedimento_entrega_so_a_pasta_cega(self):
        texto = " ".join((ENTREGA / "avaliacoes" / "ENSAIO-CONTRASTIVO.md").read_text(encoding="utf-8").split())
        self.assertIn("--destino", texto)
        self.assertIn("só a pasta cega", texto)
        self.assertNotIn("Dar as notas em `cego/notas.json`", texto)


if __name__ == "__main__":
    unittest.main()
