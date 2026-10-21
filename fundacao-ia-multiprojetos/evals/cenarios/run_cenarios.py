#!/usr/bin/env python3
"""Executor determinístico dos cenários de avaliação da skill (ambientes descartáveis).

Cada cenário cria sua própria pasta temporária, usa os scripts e o kit da skill como um
executor faria e registra, por verificação: esperado, observado, resultado e evidência.
Tipos: "real-local" (execução real no computador, sem provedores externos),
"simulado" (identidades/provedores de ensaio rotulados), "estrutural" (validação de arquivos).

Uso: python run_cenarios.py --saida <pasta-de-resultados> [--manter] [--so CEN-01,CEN-05]
Código 0 se todas as verificações passarem.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
SCRIPTS = SKILL / "scripts"
KIT = SKILL / "assets" / "fundacao-kit"
FIX = SKILL / "evals" / "fixtures"
PY = sys.executable
BASE_ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}
BASE_ENV.pop("FUNDACAO_PRINCIPAL", None)


def run(cmd, cwd=None, env=None, timeout=600, stdin=None):
    return subprocess.run([str(c) for c in cmd], cwd=str(cwd) if cwd else None, env=env or BASE_ENV,
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, input=stdin)


def kit_cli(root: Path, args: list[str], principal: str | None = None):
    env = dict(BASE_ENV)
    if principal:
        env["FUNDACAO_PRINCIPAL"] = principal
    return run([PY, "-B", "-m", "fundacao", "--raiz", root, *args], cwd=root, env=env)


class Cenario:
    def __init__(self, cid: str, nome: str, tipo: str, requisitos: str):
        self.id, self.nome, self.tipo, self.requisitos = cid, nome, tipo, requisitos
        self.checks: list[dict] = []
        self.erro: str | None = None
        self.bloqueio: str | None = None

    def check(self, descricao: str, esperado, observado, passou: bool, evidencia: str = ""):
        self.checks.append({"verificacao": descricao, "esperado": str(esperado), "observado": str(observado)[:400],
                            "passou": bool(passou), "evidencia": evidencia[:400]})

    def pulada(self, descricao: str, motivo: str):
        """Verificação que não pôde rodar neste ambiente: fica visível no resultado (não conta como aprovada
        nem reprova o cenário) em vez de sumir em silêncio (auditoria final da 1.4.2, AF-05)."""
        self.checks.append({"verificacao": descricao, "esperado": "executada", "observado": f"PULADA: {motivo}",
                            "passou": None, "pulada": True, "evidencia": motivo[:400]})

    def bloquear(self, motivo: str):
        """Dependência opcional ausente neste ambiente (torch, transformers, mcp): o cenário não roda e fica
        BLOQUEADO, nunca PASSOU; reprova a execução, salvo com --opcionais-ausentes-bloqueiam (só a CI pública)."""
        self.bloqueio = motivo

    @property
    def passou(self) -> bool:
        return (self.erro is None and self.bloqueio is None and bool(self.checks)
                and all(c["passou"] for c in self.checks if not c.get("pulada")))

    def as_dict(self) -> dict:
        return {"id": self.id, "nome": self.nome, "tipo": self.tipo, "requisitos": self.requisitos,
                "passou": self.passou, "bloqueado": self.bloqueio, "erro": self.erro, "verificacoes": self.checks}


def situacao(r: dict) -> str:
    return "BLOQUEADO" if r.get("bloqueado") else ("PASSOU" if r["passou"] else "FALHOU")


def codigo_de_saida(resultados: list[dict], opcionais_bloqueiam: bool = False) -> int:
    """0 se todos passaram; com `opcionais_bloqueiam`, cenário bloqueado por dependência opcional não reprova."""
    ruins = [r for r in resultados if not r["passou"] and not (opcionais_bloqueiam and r.get("bloqueado"))]
    return 0 if not ruins else 1


def nova_fundacao_api(root: Path):
    """Fundação de ensaio via API do kit (para cenários que testam a lógica em processo)."""
    for name in ("fundacao", "registry", "templates"):
        shutil.copytree(KIT / name, root / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    sys.path.insert(0, str(root))
    from fundacao.core.auth import Policy, Principal, resource_case, resource_project
    from fundacao.core.db import connect
    from fundacao.core.projects import create_project
    con = connect(root / "state" / "state.sqlite")
    pol = Policy(con)
    pol.bootstrap_admin("titular")
    adm = Principal("titular", "teste-simulado")
    create_project(root, con, adm, "juridico-lab", "Laboratório jurídico", "fluxos fictícios")
    create_project(root, con, adm, "reversa-lab", "Laboratório de software", "CaixaSim")
    for p in ("operador-juridico", "operador-engenharia", "revisor-juridico", "curador-comum"):
        pol.register_principal(adm, p)
    for a in ("read", "write", "use"):
        pol.grant(adm, "operador-juridico", resource_project("juridico-lab"), a)
        pol.grant(adm, "operador-engenharia", resource_project("reversa-lab"), a)
    for a in ("read", "approve", "audit"):
        pol.grant(adm, "revisor-juridico", resource_project("juridico-lab"), a)
    pol.grant(adm, "operador-juridico", resource_case("juridico-lab", "caso-fic-001"), "read")
    for p in ("operador-juridico", "operador-engenharia", "revisor-juridico", "curador-comum"):
        pol.grant(adm, p, "common", "read")
    pol.grant(adm, "curador-comum", "common", "curate")
    sim = lambda pid: Principal(pid, "teste-simulado")  # noqa: E731
    return con, adm, sim


def descarregar_modulos_fundacao():
    for name in list(sys.modules):
        if name == "fundacao" or name.startswith("fundacao."):
            del sys.modules[name]
    sys.path[:] = [p for p in sys.path if "fundacao-cen" not in p]


# ----------------------------------------------------------------------------- cenários
def cen01(W: Path) -> Cenario:
    c = Cenario("CEN-01", "Fundação nova com dois projetos (Fluxo A)", "real-local; identidades de ensaio",
                "R01 R02 R03 R04 R16 R44 R50 R54")
    root = W / "f1"
    r1 = run([PY, "-B", SCRIPTS / "instalar_kit.py", "--destino", root])
    rec1 = json.loads(r1.stdout)
    c.check("instalação do kit copia arquivos e registra hashes", "copiados > 0 com sha256",
            len(rec1["copiados"]), len(rec1["copiados"]) > 0 and all("sha256" in x for x in rec1["copiados"]))
    rec2 = json.loads(run([PY, "-B", SCRIPTS / "instalar_kit.py", "--destino", root]).stdout)
    c.check("reinstalação é idempotente", "0 copiados, 0 conflitos",
            f"{len(rec2['copiados'])} copiados, {len(rec2['conflitos_preservados'])} conflitos",
            not rec2["copiados"] and not rec2["conflitos_preservados"])
    r = kit_cli(root, ["init", "--admin", "titular"])
    c.check("init cria o primeiro administrador", "admin_criado=titular", r.stdout.strip()[:120],
            r.returncode == 0 and json.loads(r.stdout)["admin_criado"] == "titular")
    for pid, nome in (("juridico-lab", "Laboratório jurídico"), ("reversa-lab", "Laboratório de software")):
        r = kit_cli(root, ["projeto", "criar", "--id", pid, "--nome", nome, "--finalidade", "ensaio"], "titular")
        c.check(f"projeto {pid} criado pelo modelo", "código 0", r.returncode, r.returncode == 0)
    r = kit_cli(root, ["projeto", "criar", "--id", "juridico-lab", "--nome", "x", "--finalidade", "x"], "titular")
    c.check("recriação informa existência sem sobrescrever", "código 2 e E_EXISTS", r.stderr.strip()[:120],
            r.returncode == 2 and "E_EXISTS" in r.stderr)
    for p in ("operador-juridico", "operador-engenharia"):
        kit_cli(root, ["acl", "registrar", "--principal", p], "titular")
    for act in ("read", "write"):
        kit_cli(root, ["acl", "conceder", "--principal", "operador-juridico", "--recurso", "project:juridico-lab",
                       "--acao-permitida", act], "titular")
        kit_cli(root, ["acl", "conceder", "--principal", "operador-engenharia", "--recurso", "project:reversa-lab",
                       "--acao-permitida", act], "titular")
    t = kit_cli(root, ["tarefa", "criar", "--projeto", "juridico-lab", "--objetivo",
                       "listar documentos do caso Aurora (fictício)", "--chave", "aurora-001"], "operador-juridico")
    tid = json.loads(t.stdout)["task_id"]
    v = kit_cli(root, ["tarefa", "ver", "--projeto", "juridico-lab", "--id", tid], "operador-juridico")
    c.check("tarefa persiste e é lida por processo novo", tid, v.stdout.strip()[:160],
            v.returncode == 0 and json.loads(v.stdout)["task_id"] == tid)
    n = kit_cli(root, ["tarefa", "ver", "--projeto", "juridico-lab", "--id", tid], "operador-engenharia")
    c.check("outro projeto recebe negativa sem conteúdo", "código 2, E_ACCESS_DENIED, sem 'Aurora'",
            n.stderr.strip()[:160], n.returncode == 2 and "E_ACCESS_DENIED" in n.stderr and "Aurora" not in n.stdout + n.stderr)
    st = json.loads(kit_cli(root, ["status"], "titular").stdout)
    c.check("status: cadeia de eventos íntegra e projetos visíveis ao titular", "True; 2 projetos",
            f"{st['eventos_cadeia_integra']}; {st['projetos_autorizados']}",
            st["eventos_cadeia_integra"] and len(st["projetos_autorizados"]) == 2)
    st2 = json.loads(kit_cli(root, ["status"], "operador-engenharia").stdout)
    c.check("status do operador de engenharia lista só o projeto dele", ["reversa-lab"],
            st2["projetos_autorizados"], st2["projetos_autorizados"] == ["reversa-lab"])
    log = json.loads((root / "registry" / "kit_install.json").read_text(encoding="utf-8"))
    c.check("registro de instalação com versão do kit", "kit_version presente", log[0].get("kit_version"),
            bool(log[0].get("kit_version")))
    return c


DADOS_LEGADO = ["agents", "squad.json", "painel", "casos", "squads"]  # lista positiva de dados do projeto
CODIGO_LEGADO = ["run.py", "scripts"]  # o que o componente executa: fica na fonte da fundação, nunca nos dados

COMPONENTE_LEGADO = '''"""Componente que executa o pipeline legado aprovado (adaptação sem alterar a origem).

O código executável do legado (run.py e scripts/) mora na fonte da fundação, em
`legado_peticoes_codigo/`, e não nos dados do projeto, que quem opera o projeto altera; do projeto
vêm só os casos. Antes de cada execução, a pasta aprovada é conferida contra o MANIFESTO (sha256
de TODOS os arquivos: nenhum alterado, a mais ou a menos) e os bytes conferidos são copiados para
uma pasta temporária própria, de onde o legado roda: roda exatamente o que foi conferido. O
manifesto mora neste módulo, cujo hash a habilitação grava no registro (`entrypoint_sha256`).
"""
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

CODIGO = Path(__file__).resolve().parent / "legado_peticoes_codigo"
MANIFESTO = __MANIFESTO__


def _copia_conferida(destino):
    presentes = sorted(p.relative_to(CODIGO).as_posix() for p in CODIGO.rglob("*") if p.is_file())
    if presentes != sorted(MANIFESTO):
        raise RuntimeError("código do legado difere do manifesto aprovado (arquivo a mais ou a menos); nada executado")
    for rel, esperado in MANIFESTO.items():
        dados = (CODIGO / rel).read_bytes()
        if hashlib.sha256(dados).hexdigest() != esperado:
            raise RuntimeError(f"código do legado alterado desde a aprovação ({rel}): difere do manifesto; nada executado")
        alvo = destino / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(dados)


def run(request):
    legado = (Path(request["project_dir"]) / "data" / "legado").resolve()
    caso = (legado / request["payload"]["caso"]).resolve()
    caso.relative_to(legado)  # contenção: falha se escapar da pasta do legado
    with tempfile.TemporaryDirectory(prefix="legado-peticoes-") as tmp:
        _copia_conferida(Path(tmp))
        # -E -s: nem PYTHONPATH nem o site do usuário entram no import; -X utf8 mantém a saída em UTF-8.
        proc = subprocess.run([sys.executable, "-B", "-E", "-s", "-X", "utf8", str(Path(tmp) / "run.py"), str(caso)],
                              cwd=str(legado), capture_output=True, text=True, encoding="utf-8", timeout=20)
    return {"codigo": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
'''

WRAPPER = '''import os
import sys
from pathlib import Path

raiz = Path(os.environ["FUNDACAO_RAIZ"])
sys.path.insert(0, str(raiz))
from fundacao.core.auth import principal_from_env  # noqa: E402
from fundacao.core.components import dispatch  # noqa: E402
from fundacao.core.db import connect  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
con = connect(raiz / "state" / "state.sqlite")
res = dispatch(raiz, con, principal_from_env(con), "peticoes-legado", "legado_peticoes",
               {"caso": "casos/" + Path(sys.argv[1]).name})["result"]
sys.stdout.write(res["stdout"])
sys.stderr.write(res["stderr"])
sys.exit(res["codigo"])
'''

ADAPTADOR = '''"""Adaptador do manifesto legado: agentes como objetos -> lista canônica de identificadores."""
import json
import sys
from pathlib import Path

origem, destino = Path(sys.argv[1]), Path(sys.argv[2])
squad = json.loads(origem.read_text(encoding="utf-8"))
canonico = {"name": squad["name"], "agents": [a["id"] if isinstance(a, dict) else a for a in squad["agents"]]}
destino.write_text(json.dumps(canonico, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
'''


def _escrever_se_diferente(path: Path, texto: str) -> str:
    if path.exists() and path.read_text(encoding="utf-8") == texto:
        return "ja-existia"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(texto, encoding="utf-8")
    return "feito"


def _codigo_aprovado(origem: Path, destino: Path) -> tuple[str, dict[str, str]]:
    """Copia o código executável do legado (CODIGO_LEGADO, lido na origem) para a fonte da fundação e
    devolve o manifesto: sha256 de TODOS os arquivos copiados (os mesmos bytes conferidos). Idempotente."""
    manifesto, feito = {}, False
    for item in CODIGO_LEGADO:
        base = origem / item
        for p in sorted([base] if base.is_file() else base.rglob("*")):
            rel = p.relative_to(origem)
            if not p.is_file() or "__pycache__" in rel.parts:
                continue
            dados = p.read_bytes()
            manifesto[rel.as_posix()] = hashlib.sha256(dados).hexdigest()
            alvo = destino / rel
            if not (alvo.is_file() and alvo.read_bytes() == dados):
                alvo.parent.mkdir(parents=True, exist_ok=True)
                alvo.write_bytes(dados)
                feito = True
    return ("feito" if feito else "ja-existia"), manifesto


def _registrar_e_habilitar(root: Path, entrada: dict) -> str:
    """Registra o componente desabilitado e o habilita pela fundação (`componente habilitar`, só a
    administração): a habilitação grava o `entrypoint_sha256` do módulo, que traz o manifesto do código
    do legado — todo o código executado fica amarrado ao aprovado. Já registrado, habilitado e com o
    mesmo hash: 'ja-existia'."""
    cid = entrada["component_id"]
    reg = root / "registry" / "components" / f"{cid}.json"
    modulo = root / "fundacao" / "components" / f"{cid}.py"
    aprovado = {**entrada, "enabled": True, "entrypoint_sha256": hashlib.sha256(modulo.read_bytes()).hexdigest()}
    try:
        if json.loads(reg.read_text(encoding="utf-8")) == aprovado:
            return "ja-existia"
    except (OSError, json.JSONDecodeError):
        pass
    reg.parent.mkdir(parents=True, exist_ok=True)
    reg.write_text(json.dumps({**entrada, "enabled": False}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    r = kit_cli(root, ["componente", "habilitar", "--id", cid], "titular")
    return "feito" if r.returncode == 0 else f"falhou: {r.stderr[-200:]}"


def adaptar(W: Path, root: Path, origem: Path, concluir: bool = True) -> list[tuple[str, str]]:
    """Executor de referência do Fluxo B (etapas B6–B9), idempotente. O projeto recebe só dados; o código
    que o componente executa vai para a fonte da fundação com manifesto de hashes, e a habilitação passa
    pela fundação (auditoria 1.5.0, achado 6). `concluir=False` para no estado interrompido do E3:
    dados, código, adaptador e módulo escritos; componente não registrado nem habilitado; sem invólucro."""
    passos = []
    trabalho = W / "trabalho-legado"
    if not trabalho.exists():
        shutil.copytree(origem, trabalho, ignore=shutil.ignore_patterns(".env", "__pycache__"))
        passos.append(("cópia de trabalho", "feito"))
    else:
        passos.append(("cópia de trabalho", "ja-existia"))
    golden = W / "ref" / "golden.json"
    if not golden.exists():
        r = run([PY, "-B", SCRIPTS / "caracterizar.py", "gravar", "--entradas", str(trabalho / "casos" / "*.json"),
                 "--saida", golden, "--cwd", trabalho, "--pasta-saida", trabalho / "saida", "--",
                 PY, "-B", "run.py", "{entrada}"])
        passos.append(("caracterização (golden)", "feito" if r.returncode == 0 else f"falhou: {r.stderr[-200:]}"))
    else:
        passos.append(("caracterização (golden)", "ja-existia"))
    if not (root / "state" / "state.sqlite").exists():
        run([PY, "-B", SCRIPTS / "instalar_kit.py", "--destino", root])
        kit_cli(root, ["init", "--admin", "titular"])
        passos.append(("fundação de destino", "feito"))
    else:
        passos.append(("fundação de destino", "ja-existia"))
    r = kit_cli(root, ["projeto", "criar", "--id", "peticoes-legado", "--nome", "Petições (legado)",
                       "--finalidade", "squad de petições adaptado"], "titular")
    passos.append(("registro do projeto", "feito" if r.returncode == 0 else
                   ("ja-existia" if "E_EXISTS" in r.stderr else f"falhou: {r.stderr[-200:]}")))
    dest = root / "projects" / "peticoes-legado" / "data" / "legado"
    copiou = False
    for item in DADOS_LEGADO:  # lista positiva: nada de .env, memória, saídas antigas ou código executado
        src, dst = origem / item, dest / item
        if dst.exists():
            continue
        copiou = True
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    passos.append(("dados do legado no projeto (lista positiva)", "feito" if copiou else "ja-existia"))
    estado, manifesto = _codigo_aprovado(origem, root / "fundacao" / "components" / "legado_peticoes_codigo")
    passos.append(("código do legado na fonte da fundação (manifesto)", estado))
    passos.append(("adaptador do manifesto", _escrever_se_diferente(
        root / "projects" / "peticoes-legado" / "data" / "adaptadores" / "squad_canonico.py", ADAPTADOR)))
    run([PY, "-B", root / "projects" / "peticoes-legado" / "data" / "adaptadores" / "squad_canonico.py",
         dest / "squad.json", dest / "squad.canonico.json"])
    passos.append(("componente legado_peticoes", _escrever_se_diferente(
        root / "fundacao" / "components" / "legado_peticoes.py",
        COMPONENTE_LEGADO.replace("__MANIFESTO__", json.dumps(manifesto, indent=4, sort_keys=True)))))
    for act in ("read", "use"):
        kit_cli(root, ["acl", "conceder", "--principal", "titular", "--recurso", "project:peticoes-legado",
                       "--acao-permitida", act], "titular")
    if not concluir:
        return passos
    entrada = {"schema_version": "fundacao.component/1", "component_id": "legado_peticoes", "version": "1.0.0",
               "kind": "workflow", "purpose": "pipeline legado de petições, executado sem alterar a origem",
               "enabled": False, "entrypoint": "fundacao.components.legado_peticoes:run",
               "allowed_projects": ["peticoes-legado"], "permissions": ["legado:executar"],
               "timeout_seconds": 30, "requires_modules": [], "evidence": []}
    passos.append(("registro do componente", _registrar_e_habilitar(root, entrada)))
    passos.append(("invólucro de execução via fundação", _escrever_se_diferente(W / "ferramentas" / "executar_via_fundacao.py", WRAPPER)))
    return passos


def _comparar_golden(W: Path, root: Path):
    saida = root / "projects" / "peticoes-legado" / "data" / "legado" / "saida"
    shutil.rmtree(saida, ignore_errors=True)  # saídas derivadas são regeneradas
    env = {k: v for k, v in BASE_ENV.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    env.update({"FUNDACAO_RAIZ": str(root), "FUNDACAO_PRINCIPAL": "titular"})  # sem modo UTF-8 de propósito
    return run([PY, "-B", SCRIPTS / "caracterizar.py", "comparar", "--golden", W / "ref" / "golden.json",
                "--pasta-saida", saida, "--", PY, "-B", W / "ferramentas" / "executar_via_fundacao.py", "{entrada}"],
               env=env)


def cen02(W: Path) -> Cenario:
    c = Cenario("CEN-02", "Projeto existente adaptado à fundação (Fluxo B)", "real-local",
                "R02 R04 R32 R44 R53 + procedimento B1–B10")
    origem = W / "origem-legado"
    shutil.copytree(FIX / "legado-squad", origem)
    m0 = W / "ref" / "manifesto-origem.json"
    run([PY, "-B", SCRIPTS / "manifesto.py", "criar", "--raiz", origem, "--saida", m0, "--rotulo", "baseline-b-001"])
    man = json.loads(m0.read_text(encoding="utf-8"))
    c.check("manifesto da origem exclui o arquivo de segredo sem lê-lo", ".env em excluidos",
            [e["path"] for e in man["excluidos"]], any(e["path"] == ".env" for e in man["excluidos"]))
    s = json.loads(run([PY, "-B", SCRIPTS / "sinais_compatibilidade.py", "--raiz", origem]).stdout)
    c.check("classificação sugerida para o legado", "adaptação por interfaces", s["classe_sugerida"],
            s["classe_sugerida"] == "adaptação por interfaces")
    passos = adaptar(W, W / "f2", origem)
    c.check("etapas da adaptação executadas", "todas 'feito'", passos, all(p[1] == "feito" for p in passos))
    trabalho = W / "trabalho-legado"
    painel_origem = run([PY, "-B", "painel/leitor.py", "squad.json"], cwd=trabalho)
    c.check("defeito de contrato reproduzido na cópia (painel × manifesto)", "código ≠ 0 (TypeError)",
            painel_origem.returncode, painel_origem.returncode != 0 and "TypeError" in painel_origem.stderr)
    legado = W / "f2" / "projects" / "peticoes-legado" / "data" / "legado"
    painel_adapt = run([PY, "-B", "painel/leitor.py", "squad.canonico.json"], cwd=legado)
    c.check("painel funciona com o adaptador, sem alterar a origem", "Agentes: triagem, redator",
            painel_adapt.stdout.strip(), painel_adapt.returncode == 0 and "triagem, redator" in painel_adapt.stdout)
    cmp = _comparar_golden(W, W / "f2")
    res = json.loads(cmp.stdout) if cmp.stdout.strip().startswith("{") else {"divergencias": ["saida invalida"]}
    c.check("comportamento antes × depois idêntico (golden master)", "0 divergências em 3 casos",
            f"{len(res.get('divergencias', []))} divergências; casos={res.get('casos')}",
            cmp.returncode == 0 and res.get("casos") == 3 and not res["divergencias"],
            "inclui caso inválido (código 2) e fato sem fonte virando pendência")
    v = run([PY, "-B", SCRIPTS / "manifesto.py", "verificar", "--raiz", origem, "--manifesto", m0])
    c.check("origem inalterada (manifesto)", "sem alterados/ausentes/novos", v.stdout.strip()[:160], v.returncode == 0)
    c.check("segredo não copiado para o projeto", "sem .env no projeto",
            sorted(p.name for p in legado.iterdir()), not (legado / ".env").exists())
    ret = W / "RETOMADA.md"
    run([PY, "-B", SCRIPTS / "retomada.py", "criar", "--saida", ret])
    texto = ret.read_text(encoding="utf-8")
    preench = {
        "project_id:": "peticoes-legado", "run_id de referência:": "adaptacao-b-001",
        "Objetivo atual:": "adaptar o squad de petições à fundação preservando o comportamento",
        "Estado confirmado:": "golden master igual antes/depois; origem inalterada",
        "Versão do código/configuração:": "kit 1.0.0; manifesto baseline-b-001",
        "Evidências:": "ref/golden.json; ref/manifesto-origem.json",
        "Próxima ação autorizada:": "migrar o painel para o formato canônico (decisão do titular)",
        "Ações já realizadas que não devem ser repetidas:": "registro do projeto; registro do componente",
        "Bloqueios de acesso, custo ou decisão:": "nenhum",
        "Última conferência do registro:": time.strftime("%Y-%m-%d %H:%M %z"),
    }
    linhas = []
    for linha in texto.splitlines():
        for chave, valor in preench.items():
            if linha.startswith(chave):
                linha = f"{chave} {valor}"
        linhas.append(linha)
    linhas = [("1. ref/golden.json" if l.strip() == "1. (preencher)" else l) for l in linhas]
    ret.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    rv = run([PY, "-B", SCRIPTS / "retomada.py", "validar", "--arquivo", ret])
    c.check("RETOMADA com campos mínimos preenchidos", "ok", rv.stdout.strip()[:160], rv.returncode == 0)
    return c


def cen03(W: Path) -> Cenario:
    c = Cenario("CEN-03", "Reexecução sobre projeto parcialmente adaptado", "real-local", "R02 R08 R46 + B9")
    origem = W / "origem-legado"
    shutil.copytree(FIX / "legado-squad", origem)
    root = W / "f3"
    adaptar(W, root, origem)  # primeira passagem
    (root / "registry" / "components" / "legado_peticoes.json").unlink()  # interrupção no meio
    passos = adaptar(W, root, origem)  # reexecução
    feitos = [p[0] for p in passos if p[1] == "feito"]
    c.check("reexecução refaz só o que faltava", "apenas 'registro do componente'", feitos,
            feitos == ["registro do componente"])
    passos3 = adaptar(W, root, origem)
    c.check("terceira passagem não altera nada", "todas as etapas 'ja-existia'",
            [p for p in passos3 if p[1] != "ja-existia"] or "todas ja-existia",
            all(p[1] == "ja-existia" for p in passos3))
    sys.path.insert(0, str(root))
    import sqlite3
    con = sqlite3.connect(str(root / "state" / "state.sqlite"))
    n = con.execute("SELECT COUNT(*) FROM event WHERE kind='project_created' AND project_id='peticoes-legado'").fetchone()[0]
    nproj = con.execute("SELECT COUNT(*) FROM project WHERE project_id='peticoes-legado'").fetchone()[0]
    con.close()
    c.check("sem duplicação de projeto ou evento de criação", "1 e 1", f"{nproj} e {n}", n == 1 and nproj == 1)
    cmp = _comparar_golden(W, root)
    c.check("comportamento preservado após reexecuções", "código 0", cmp.returncode, cmp.returncode == 0)
    d = json.loads(kit_cli(root, ["projeto", "drift", "--id", "peticoes-legado"], "titular").stdout)
    c.check("atualização do modelo ≠ migração da instância", "migration_needed=False",
            d["migration_needed"], d["migration_needed"] is False)
    return c


def cen04(W: Path) -> Cenario:
    c = Cenario("CEN-04", "Projeto incompatível nas condições atuais", "real-local (análise estática)", "B3; R04 R53")
    s = json.loads(run([PY, "-B", SCRIPTS / "sinais_compatibilidade.py", "--raiz", FIX / "legado-incompativel"]).stdout)
    c.check("classe sugerida não é integração direta", "bloqueio nas condições atuais", s["classe_sugerida"],
            s["classe_sugerida"] == "bloqueio nas condições atuais")
    sig = s["sinais"]
    c.check("sinais objetivos detectados", "caminho absoluto, escape, credencial, rede",
            {k: len(v) for k, v in sig.items()},
            all(sig[k] for k in ("caminho_absoluto", "escape_da_raiz", "credencial_embutida", "rede_ou_servico_externo")))
    texto = json.dumps(s, ensure_ascii=False)
    c.check("valor da credencial não aparece no relatório", "ausente", "chave-embutida-ficticia" in texto,
            "chave-embutida-ficticia" not in texto)
    return c


def cen05(W: Path) -> Cenario:
    c = Cenario("CEN-05", "Dependência indisponível: bloquear e avançar no independente", "real-local; simulado (rotas)",
                "R12 R14 R27 R32")
    root = W / "fundacao-cen05"
    con, adm, sim = nova_fundacao_api(root)
    try:
        from fundacao.core import components
        from fundacao.core.contracts import DependencyUnavailable
        reg = root / "registry" / "components"
        (reg / "dependente.json").write_text(json.dumps({
            "schema_version": "fundacao.component/1", "component_id": "dependente", "version": "0.1.0", "kind": "tool",
            "enabled": True, "entrypoint": "fundacao.components.source_manifest:run", "allowed_projects": ["juridico-lab"],
            "permissions": [], "timeout_seconds": 10, "requires_modules": ["modulo_inexistente_xyz"]}), encoding="utf-8")
        inv = {x["component_id"]: x for x in components.discover(root)}
        c.check("inventário mostra dependência ausente", "dependencia_ausente", inv["dependente"]["health"],
                inv["dependente"]["health"] == "dependencia_ausente")
        try:
            components.dispatch(root, con, sim("operador-juridico"), "juridico-lab", "dependente", {})
            ok = False
        except DependencyUnavailable:
            ok = True
        c.check("despacho recusado antes de executar", "DependencyUnavailable", ok, ok)
        entry = json.loads((reg / "source_manifest.json").read_text(encoding="utf-8"))
        entry.update(enabled=True, allowed_projects=["juridico-lab"])
        (reg / "source_manifest.json").write_text(json.dumps(entry), encoding="utf-8")
        data = root / "projects" / "juridico-lab" / "data"
        (data / "doc.md").write_text("FICTÍCIO", encoding="utf-8")
        (data / "catalog.json").write_text(json.dumps({"doc-1": "doc.md"}), encoding="utf-8")
        res = components.dispatch(root, con, sim("operador-juridico"), "juridico-lab", "source_manifest",
                                  {"document_ids": ["doc-1"]})
        c.check("trabalho independente continua", "manifesto com 1 arquivo", len(res["result"]["files"]),
                len(res["result"]["files"]) == 1)
        from fundacao.adapters.base import ProviderRequest
        from fundacao.core.routing import DEFAULT_POLICY, Router
        pol = json.loads(json.dumps(DEFAULT_POLICY))
        pol["routes"]["simulado"]["enabled"] = False
        out = Router(con, sim("operador-juridico"), pol, {}).call("default", ProviderRequest("juridico-lab", "t", "r", "x"))
        c.check("sem rota autorizada a tarefa fica bloqueada com motivos", "blocked + motivos por rota",
                out["attempts"], out["state"] == "blocked" and all("skipped" in a for a in out["attempts"]))
    finally:
        con.close()
        descarregar_modulos_fundacao()
    corpus = W / "corpus.md"
    corpus.write_text("Toda minuta recebe revisão humana antes da entrega.", encoding="utf-8")
    r = run([PY, "-B", SCRIPTS / "cag_kv_demo.py", "--modelo", W / "modelo-inexistente", "--corpus", corpus,
             "--pergunta", "Quem revisa?"])
    estado = json.loads(r.stdout).get("estado") if r.stdout.strip().startswith("{") else r.stdout[:80]
    c.check("CAG sem modelo autorizado: bloqueio explícito, sem download", "código 3; estado=bloqueado",
            f"{r.returncode}; {estado}", r.returncode == 3 and estado == "bloqueado")
    return c


FLUXO_FILHO = '''import sys
from pathlib import Path
raiz = Path(sys.argv[1]); modo = sys.argv[2]
sys.path.insert(0, str(raiz))
from fundacao.core.auth import Principal
from fundacao.core.db import connect
from fundacao.core.tasks import Coordinator, StepDef, Budget
con = connect(raiz / "state" / "state.sqlite")
coord = Coordinator(raiz, con, Principal("operador-juridico", "teste-simulado"), "juridico-lab")
task = coord.create_task("relatório do caso Aurora", idempotency_key="aurora-relatorio")
fluxo = [StepDef("conferir", inputs=("relato.md",)), StepDef("extrair", depends_on=("conferir",)),
         StepDef("redigir", depends_on=("extrair",))]
run_id = coord.start_run(task, "relatorio", "1", fluxo, Budget(max_calls=2))
cont = raiz / "execucoes.txt"
def h(nome):
    def f(ctx):
        with open(cont, "a", encoding="utf-8") as fh:
            fh.write(nome + "\\n")
        return nome + " ok"
    return f
handlers = {s.step_id: h(s.step_id) for s in fluxo}
if modo == "primeira":
    coord.run(run_id, handlers, interrupt=("extrair", "before_commit"))
else:
    res = coord.resume(run_id, handlers, now=10**12)
    print(res["state"])
'''


def cen06(W: Path) -> Cenario:
    c = Cenario("CEN-06", "Falha no meio da execução e retomada em outro processo", "real-local",
                "R06 R07 R08 R39 R41 R48")
    root = W / "fundacao-cen06"
    con, adm, sim = nova_fundacao_api(root)
    (root / "projects" / "juridico-lab" / "data" / "relato.md").write_text("Pagamento em abril. FICTÍCIO", encoding="utf-8")
    con.close()
    descarregar_modulos_fundacao()
    filho = W / "fluxo_filho.py"
    filho.write_text(FLUXO_FILHO, encoding="utf-8")
    p1 = run([PY, "-B", filho, root, "primeira"])
    c.check("primeiro processo interrompido após gravar a saída e antes de confirmar", "código ≠ 0 (SimulatedInterrupt)",
            p1.returncode, p1.returncode != 0 and "SimulatedInterrupt" in p1.stderr)
    p2 = run([PY, "-B", filho, root, "retomar"])
    c.check("retomada em processo novo conclui", "succeeded", p2.stdout.strip()[-40:], p2.stdout.strip().endswith("succeeded"))
    execs = (root / "execucoes.txt").read_text(encoding="utf-8").split()
    c.check("efeito confirmado não repetido (extrair executou 1 vez)", "extrair=1; conferir=1; redigir=1",
            {k: execs.count(k) for k in set(execs)}, execs.count("extrair") == 1 and execs.count("conferir") == 1)
    import sqlite3
    db = sqlite3.connect(str(root / "state" / "state.sqlite"))
    rec = db.execute("SELECT COUNT(*) FROM event WHERE kind='step_reconciled'").fetchone()[0]
    db.close()
    c.check("reconciliação pelo recibo registrada", 1, rec, rec == 1)
    sys.path.insert(0, str(root))
    from fundacao.core import events as ev
    from fundacao.core.db import connect
    con2 = connect(root / "state" / "state.sqlite")
    ok, bad = ev.verify_chain(con2)
    con2.close()
    descarregar_modulos_fundacao()
    c.check("execução reconstruível: cadeia de eventos íntegra", True, ok, ok)
    ret = W / "RETOMADA-vazia.md"
    run([PY, "-B", SCRIPTS / "retomada.py", "criar", "--saida", ret])
    rv = run([PY, "-B", SCRIPTS / "retomada.py", "validar", "--arquivo", ret])
    faltas = json.loads(rv.stdout)["campos_ausentes"]
    c.check("RETOMADA incompleta é recusada", "código 1 com campos ausentes", f"{rv.returncode}; {len(faltas)} campos",
            rv.returncode == 1 and "efeitos já realizados" in faltas)
    return c


def cen07(W: Path) -> Cenario:
    c = Cenario("CEN-07", "Tentativa de acesso entre projetos (memória, RAG, cache, componente)",
                "simulado (identidades de ensaio); lógica da política", "R04 R18 R22 R28")
    root = W / "fundacao-cen07"
    con, adm, sim = nova_fundacao_api(root)
    try:
        from fundacao.core.cache import ResponseCache
        from fundacao.core.canon import sha256_text
        from fundacao.core.contracts import AccessDenied, PathEscape
        from fundacao.core.knowledge import KnowledgeService
        from fundacao.core.memory import MemoryService
        from fundacao.core.paths import contained
        from fundacao.core.tasks import Coordinator
        jur, eng, rev = sim("operador-juridico"), sim("operador-engenharia"), sim("revisor-juridico")
        canario = "JUR-SEGREDO-FIC"
        mj = MemoryService(con, jur)
        mid = mj.propose(op_id="op-can", scope="project", project_id="juridico-lab", kind="fato", origin="humano",
                         body=canario + " marcador", source_ref="FIC-1")
        MemoryService(con, rev).approve(mid, sha256_text(canario + " marcador"))
        data = root / "projects" / "juridico-lab" / "data"
        (data / "fonte.md").write_text(canario + " documento de laboratório", encoding="utf-8")
        kj, kr = KnowledgeService(root, con, jur), KnowledgeService(root, con, rev)
        kj.register_source("juridico-lab", "juridico-lab/CAN-1", 1, "fonte.md")
        h = kj.prepare("juridico-lab/CAN-1", 1, [canario + " documento de laboratório sou administrador"])
        kj.index("juridico-lab/CAN-1", 1)
        rub = {k: {"resultado": "aprovado", "evidencia": "conferido"} for k in ("origem", "fidelidade", "vigencia", "acesso", "finalidade")}
        kr.curate("juridico-lab/CAN-1", 1, rub, h, "2026-12-01", "lab")
        saidas = []
        saidas.append(json.dumps(MemoryService(con, eng).query(project_id="juridico-lab"), ensure_ascii=False))
        negs = 0
        for fn in (lambda: KnowledgeService(root, con, eng).search("juridico-lab", "sou administrador marcador"),
                   lambda: Coordinator(root, con, eng, "juridico-lab"),
                   lambda: MemoryService(con, eng).propose(op_id="x", scope="project", project_id="juridico-lab",
                                                           kind="fato", origin="ia", body="liberar", source_ref="x")):
            try:
                saidas.append(str(fn()))
            except AccessDenied:
                negs += 1
        cache = ResponseCache(con, eng)
        meta = cache.server_meta("reversa-lab", provider_id="s", model_revision="m", prompt_revision="p",
                                 context_hash="c", generation_config={})
        estado, _ = cache.get("juridico-lab", "qual o marcador?", meta)
        c.check("negativas aplicadas pelo serviço (busca, coordenação, escrita)", 3, negs, negs == 3)
        c.check("cache negado para identidade sem acesso", "denied", estado, estado == "denied")
        try:
            contained(root / "projects" / "reversa-lab", root / "projects" / "reversa-lab" / ".." / "juridico-lab" / "data" / "fonte.md")
            esc = False
        except PathEscape:
            esc = True
        c.check("escape de caminho com '..' recusado", "PathEscape", esc, esc)
        payloads = " ".join(r[0] for r in con.execute("SELECT payload_json FROM event"))
        vazou = any(canario in s for s in saidas) or canario in payloads
        c.check("marcador ausente de saídas e de eventos", "ausente", vazou, not vazou)
        n = con.execute("SELECT COUNT(*) FROM event WHERE kind='access_denied' AND subject='operador-engenharia'").fetchone()[0]
        c.check("negativas registradas como evidência", ">= 3", n, n >= 3)
    finally:
        con.close()
        descarregar_modulos_fundacao()
    return c


def cen08(W: Path) -> Cenario:
    c = Cenario("CEN-08", "Referência obrigatória ausente; pacote instalável sem evals/", "estrutural", "integridade da skill")
    ok = run([PY, "-B", SCRIPTS / "verificar_referencias.py", "--raiz", SKILL])
    c.check("skill íntegra: todas as referências existem", "código 0", ok.stdout.strip()[-120:], ok.returncode == 0)
    copia = W / "skill-copia"
    shutil.copytree(SKILL, copia, ignore=shutil.ignore_patterns("__pycache__", "fixtures", "*.pyc"))
    (copia / "references" / "fluxo-b-adaptar.md").unlink()
    r = run([PY, "-B", copia / "scripts" / "verificar_referencias.py", "--raiz", copia])
    faltas = json.loads(r.stdout)["ausentes"]
    alvo = [f for f in faltas if "fluxo-b-adaptar.md" in f["referencia"]]
    c.check("remoção de referência detectada com o caminho", "código 1 citando references/fluxo-b-adaptar.md",
            f"{r.returncode}; {len(alvo)} citações", r.returncode == 1 and alvo)
    pacote = W / "pacote" / SKILL.name  # como o .skill: sem evals/
    shutil.copytree(SKILL, pacote, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "evals"))
    p = run([PY, "-B", pacote / "scripts" / "verificar_referencias.py", "--raiz", pacote])
    res = json.loads(p.stdout)
    c.check("pacote instalável (sem evals/) passa na verificação de referências", "código 0; citações a evals/ à parte",
            f"{p.returncode}; ausentes={len(res['ausentes'])}; fora do pacote={len(res['fora_do_pacote_instalavel'])}",
            p.returncode == 0 and not res["ausentes"])
    # Cada arquivo citado como `<skill>/…` (inclusive dentro de comandos com espaços) some, um de
    # cada vez, numa cópia: o verificador precisa acusar a ausência.
    citados = sorted({m.group(1) for md in SKILL.rglob("*.md") if md.relative_to(SKILL).parts[0] != "evals"
                      for m in re.finditer(r"<skill>/([A-Za-z0-9_./\-]*[A-Za-z0-9_\-])", md.read_text(encoding="utf-8"))
                      if (SKILL / m.group(1)).is_file()})
    copia2 = W / "skill-copia-2"
    shutil.copytree(SKILL, copia2, ignore=shutil.ignore_patterns("__pycache__", "fixtures", "*.pyc"))
    nao_pegos = []
    for rel in citados:
        alvo2 = copia2 / rel
        guardado = alvo2.with_name(alvo2.name + ".guardado")
        alvo2.rename(guardado)
        try:
            r2 = run([PY, "-B", SCRIPTS / "verificar_referencias.py", "--raiz", copia2])
            faltas2 = json.loads(r2.stdout)["ausentes"]
            if r2.returncode != 1 or not any(rel in f["referencia"] for f in faltas2):
                nao_pegos.append(rel)
        finally:
            guardado.rename(alvo2)
    c.check("cada arquivo citado como `<skill>/…`, inclusive dentro de comandos, é conferido",
            "todas as remoções acusadas", f"{len(citados) - len(nao_pegos)} de {len(citados)}; não acusados: {nao_pegos}",
            bool(citados) and not nao_pegos)
    # Por ocorrência: um erro plantado em CADA citação `<skill>/…` (uma de cada vez) tem de ser acusado,
    # mesmo quando o arquivo também é citado em outro lugar.
    ocorrencias = []
    for md in sorted(SKILL.rglob("*.md")):
        rel_md = md.relative_to(SKILL)
        if rel_md.parts[0] == "evals":
            continue
        for m in re.finditer(r"<skill>/([A-Za-z0-9_./\-]*[A-Za-z0-9_\-])", md.read_text(encoding="utf-8")):
            ocorrencias.append((rel_md, m.start(1), m.end(1)))
    escapam = []
    for k, (rel_md, ini, fim) in enumerate(ocorrencias):
        arq = copia2 / rel_md
        original = arq.read_text(encoding="utf-8")
        caminho = original[ini:fim]
        primeira, _, resto = caminho.partition("/")
        # Três erros por ocorrência: arquivo inexistente, erro na primeira pasta e caixa trocada
        # (passaria num sistema de arquivos que não distingue maiúsculas, mas não no Linux).
        trocada = primeira[:1].upper() + primeira[1:] if primeira[:1].islower() else primeira[:1].lower() + primeira[1:]
        for plantado, marca in ((f"scripts/nao-existe-{k}.py", f"nao-existe-{k}.py"),
                                (f"{primeira}x{k}/{resto}" if resto else f"{primeira}x{k}", f"{primeira}x{k}"),
                                (f"{trocada}/{resto}" if resto else trocada, f"{trocada}/{resto}" if resto else trocada)):
            arq.write_text(original[:ini] + plantado + original[fim:], encoding="utf-8", newline="\n")
            try:
                r3 = run([PY, "-B", SCRIPTS / "verificar_referencias.py", "--raiz", copia2])
                if not any(marca in f["referencia"] for f in json.loads(r3.stdout)["ausentes"]):
                    escapam.append(f"{rel_md.as_posix()}:{original.count(chr(10), 0, ini) + 1} ({plantado})")
            finally:
                arq.write_text(original, encoding="utf-8", newline="\n")
    c.check("erros plantados em cada ocorrência de `<skill>/…` (arquivo, primeira pasta e caixa) são acusados",
            "todas as ocorrências", f"{3 * len(ocorrencias) - len(escapam)} de {3 * len(ocorrencias)}; escapam: {escapam}",
            bool(ocorrencias) and not escapam)
    return c


def cen09(W: Path) -> Cenario:
    c = Cenario("CEN-09", "Backup, restauração isolada, retiradas e origem danificada", "real-local", "R31 R44 R45 R56")
    root = W / "fundacao-cen09"
    con, adm, sim = nova_fundacao_api(root)
    corpo_mem = "Preferência do cliente (FICTÍCIA) a eliminar"
    try:
        from fundacao.core.canon import sha256_text
        from fundacao.core.knowledge import KnowledgeService
        from fundacao.core.memory import MemoryService
        data = root / "projects" / "juridico-lab" / "data"
        (data / "g2.md").write_text("A lista de anexos deve apresentar o nome, a versão e a origem.", encoding="utf-8")
        kj, kr = KnowledgeService(root, con, sim("operador-juridico")), KnowledgeService(root, con, sim("revisor-juridico"))
        kj.register_source("juridico-lab", "juridico-lab/GUIA-002", 1, "g2.md")
        h = kj.prepare("juridico-lab/GUIA-002", 1, ["A lista de anexos deve apresentar o nome, a versão e a origem."])
        kj.index("juridico-lab/GUIA-002", 1)
        rub = {k: {"resultado": "aprovado", "evidencia": "conferido"} for k in ("origem", "fidelidade", "vigencia", "acesso", "finalidade")}
        kr.curate("juridico-lab/GUIA-002", 1, rub, h, "2026-12-01", "lab")
        mid = MemoryService(con, sim("operador-juridico")).propose(
            op_id="op-elim", scope="project", project_id="juridico-lab", kind="fato", origin="humano",
            body=corpo_mem, source_ref="FIC-ELIM")
        MemoryService(con, sim("revisor-juridico")).approve(mid, sha256_text(corpo_mem))
    finally:
        con.close()
    ini = kit_cli(root, ["init"])  # fundação existente: cria a identidade do registro protegido
    log = root / "state" / "retiradas.jsonl"
    ident = (json.loads(ini.stdout).get("registro_retiradas") or {}).get("identidade") if ini.returncode == 0 else None
    c.check("init cria o registro protegido com identidade", "código 0; identidade reg_…",
            f"{ini.returncode}; {ident}", ini.returncode == 0 and str(ident).startswith("reg_"))
    for passo in (["acl", "registrar", "--principal", "ex-colaborador"],
                  ["acl", "conceder", "--principal", "ex-colaborador", "--recurso", "project:juridico-lab",
                   "--acao-permitida", "read"]):
        kit_cli(root, passo, "titular")
    snap = W / "snapshot"
    neg = kit_cli(root, ["backup", "criar", "--destino", W / "snapshot-negado"], "operador-juridico")
    c.check("backup por identidade sem administração é negado", "código 2, E_ACCESS_DENIED, nada criado",
            neg.stderr.strip()[:120], neg.returncode == 2 and "E_ACCESS_DENIED" in neg.stderr
            and not (W / "snapshot-negado").exists())
    r = kit_cli(root, ["backup", "criar", "--destino", snap, "--rotulo", "baseline-a05-001"], "titular")
    c.check("backup consistente criado e com a identidade do registro anotada", "código 0, integrity ok, mesma identidade",
            f"{r.returncode}; {(json.loads(r.stdout).get('retiradas') or {}).get('log_id') if r.returncode == 0 else None}",
            r.returncode == 0 and json.loads(r.stdout)["db"]["integrity_check"] == "ok"
            and json.loads(r.stdout)["retiradas"]["log_id"] == ident)
    sys.path.insert(0, str(root))
    from fundacao.core.auth import Principal
    from fundacao.core.db import connect
    from fundacao.core.knowledge import KnowledgeService
    from fundacao.core.memory import MemoryService
    con = connect(root / "state" / "state.sqlite")
    KnowledgeService(root, con, Principal("revisor-juridico", "teste-simulado")).withdraw("juridico-lab/GUIA-002", 1, "retirada posterior")
    MemoryService(con, Principal("revisor-juridico", "teste-simulado")).withdraw(mid, "eliminação a pedido (fictício)")
    con.close()
    rev = kit_cli(root, ["acl", "revogar", "--principal", "ex-colaborador", "--recurso", "project:juridico-lab",
                         "--acao-permitida", "read"], "titular")
    c.check("revogação de acesso depois da cópia vai para o registro protegido", "código 0; linha acl_revoke",
            f"{rev.returncode}; {'acl_revoke' in log.read_text(encoding='utf-8')}",
            rev.returncode == 0 and '"acl_revoke"' in log.read_text(encoding="utf-8"))
    outra = W / "registro-de-outra-fundacao.jsonl"
    outra.write_text(log.read_text(encoding="utf-8").replace(ident, "reg_outra-fundacao"), encoding="utf-8")
    alheio = kit_cli(root, ["backup", "restaurar", "--origem", snap, "--destino", W / "restaurado-alheio",
                            "--retiradas", outra], "titular")
    c.check("registro com outra identidade NÃO libera e nada é copiado", "código 3; motivo 'identidade'; destino ausente",
            f"{alheio.returncode}; {json.loads(alheio.stdout or '{}').get('reason', '')[:60]}",
            alheio.returncode == 3 and "identidade" in json.loads(alheio.stdout).get("reason", "")
            and not (W / "restaurado-alheio").exists())
    ruim = W / "registro-malformado.jsonl"
    ruim.write_text(log.read_text(encoding="utf-8") + "{quebrado\n", encoding="utf-8")
    mal = kit_cli(root, ["backup", "restaurar", "--origem", snap, "--destino", W / "restaurado-malformado",
                         "--retiradas", ruim], "titular")
    c.check("registro malformado NÃO libera e não povoa o destino", "código 3; 'ilegível'; destino ausente",
            f"{mal.returncode}; {json.loads(mal.stdout or '{}').get('reason', '')[:60]}",
            mal.returncode == 3 and "ilegível" in json.loads(mal.stdout).get("reason", "")
            and not (W / "restaurado-malformado").exists())
    sem = kit_cli(root, ["backup", "restaurar", "--origem", snap, "--destino", W / "restaurado-sem-log"], "titular")
    c.check("sem registro de retiradas a restauração NÃO é liberada", "released=false e código 3",
            f"{json.loads(sem.stdout).get('released')}; código {sem.returncode}",
            json.loads(sem.stdout).get("released") is False and sem.returncode == 3)
    errado = kit_cli(root, ["backup", "restaurar", "--origem", snap, "--destino", W / "restaurado-caminho-errado",
                            "--retiradas", root / "state" / "retirads.jsonl"], "titular")
    c.check("caminho errado do registro de retiradas NÃO libera", "released=false, código 3, motivo 'inexistente'",
            f"{json.loads(errado.stdout).get('released')}; código {errado.returncode}",
            errado.returncode == 3 and "inexistente" in json.loads(errado.stdout).get("reason", ""))
    com = kit_cli(root, ["backup", "restaurar", "--origem", snap, "--destino", W / "restaurado", "--retiradas", log], "titular")
    rep = json.loads(com.stdout)
    c.check("restauração reaplica retiradas (fonte e memória) e a revogação antes de liberar",
            "released=true; fonte, memória e acl reaplicadas", f"{rep.get('released')}; {rep.get('reapplied')}",
            rep.get("released") and rep.get("reapplied") == ["juridico-lab/GUIA-002@1", mid,
                                                             "acl:ex-colaborador:read:project:juridico-lab"])
    lista = kit_cli(W / "restaurado", ["projeto", "listar"], "ex-colaborador")
    vistos = [p.get("project_id") for p in (json.loads(lista.stdout).get("projetos") or [])] if lista.returncode == 0 else None
    c.check("no ambiente restaurado, a identidade revogada não volta a ver o projeto", "código 0; lista vazia",
            f"{lista.returncode}; {vistos}", lista.returncode == 0 and vistos == [])
    trilha = kit_cli(W / "restaurado", ["eventos", "verificar"], "titular")
    import sqlite3 as _sq
    _db = _sq.connect(str(W / "restaurado" / "state" / "state.sqlite"))
    n_reap = _db.execute("SELECT COUNT(*) FROM event WHERE kind = 'restore_reapplied'").fetchone()[0]
    _db.close()
    c.check("a reaplicação fica na trilha restaurada, com a cadeia íntegra", "3 eventos restore_reapplied; cadeia ok",
            f"{n_reap}; {json.loads(trilha.stdout or '{}').get('cadeia_integra')}",
            n_reap == 3 and json.loads(trilha.stdout).get("cadeia_integra") is True)
    con = connect(W / "restaurado" / "state" / "state.sqlite")
    hits = KnowledgeService(W / "restaurado", con, Principal("operador-juridico", "teste-simulado")).search("juridico-lab", "anexos nome versão origem")
    mem = MemoryService(con, Principal("operador-juridico", "teste-simulado")).query(project_id="juridico-lab")
    con.close()
    c.check("fonte e memória retiradas não ressuscitam no ambiente restaurado", "0 trechos; memória ausente",
            f"{len(hits)} trechos; memória presente={corpo_mem in json.dumps(mem, ensure_ascii=False)}",
            not hits and corpo_mem not in json.dumps(mem, ensure_ascii=False))
    sobre = kit_cli(root, ["backup", "restaurar", "--origem", snap, "--destino", root, "--retiradas", log], "titular")
    codigo = (json.loads(sobre.stderr or "{}").get("error") or {}).get("code") if sobre.stderr.strip().startswith("{") else None
    c.check("restaurar sobre a origem é recusado dentro do contrato", "código 2 e erro JSON E_ARQUIVO",
            f"{sobre.returncode}; {codigo}", sobre.returncode == 2 and codigo == "E_ARQUIVO")
    alvo = snap / "files" / "projects" / "juridico-lab" / "INSTRUCOES.md"
    original = alvo.read_bytes()
    alvo.write_text("alterado", encoding="utf-8")
    pv = kit_cli(root, ["backup", "verificar", "--origem", snap], "titular")
    ver = json.loads(pv.stdout)
    c.check("alteração provocada na cópia é detectada e sai com código 3", "changed contém INSTRUCOES.md; código 3",
            f"{ver['changed']}; código {pv.returncode}",
            ver["changed"] == ["projects/juridico-lab/INSTRUCOES.md"] and pv.returncode == 3)
    alvo.write_bytes(original)
    # Banco da cópia trocado por outro íntegro (o da fundação viva, já com as retiradas posteriores):
    # a verificação confere hash e contagens contra o manifesto, e a restauração não libera.
    import sqlite3 as _sq
    dbc = snap / "state" / "state.sqlite"
    guardado = dbc.read_bytes()
    _viva, _troca = _sq.connect(str(root / "state" / "state.sqlite")), _sq.connect(str(W / "troca.sqlite"))
    _viva.backup(_troca)
    _troca.execute("PRAGMA journal_mode = DELETE")
    _troca.close()
    _viva.close()
    shutil.copy2(W / "troca.sqlite", dbc)
    tv = kit_cli(root, ["backup", "verificar", "--origem", snap], "titular")
    tr = kit_cli(root, ["backup", "restaurar", "--origem", snap, "--destino", W / "restaurado-banco-trocado",
                        "--retiradas", log], "titular")
    problemas = json.loads(tv.stdout).get("db_problemas") if tv.stdout.strip().startswith("{") else None
    c.check("banco da cópia trocado por outro íntegro não confere nem libera", "verificar 3; restaurar 3; nada copiado",
            f"{tv.returncode}; {problemas}; {tr.returncode}",
            tv.returncode == 3 and problemas and "hash do banco diferente do manifesto" in problemas
            and tr.returncode == 3 and not (W / "restaurado-banco-trocado").exists())
    dbc.write_bytes(guardado)
    descarregar_modulos_fundacao()
    db = root / "state" / "state.sqlite"
    for extra in ("state.sqlite-wal", "state.sqlite-shm"):
        (root / "state" / extra).unlink(missing_ok=True)
    db.write_bytes(b"banco corrompido de proposito")
    corr = kit_cli(root, ["backup", "restaurar", "--origem", snap, "--destino", W / "restaurado-corrompido",
                          "--retiradas", log], "titular")
    c.check("com o banco de origem corrompido, a CLI restaura autorizada pela cópia sem tocar na origem",
            "código 0, released=true, origem intacta",
            f"{corr.returncode}; origem intacta={db.read_bytes() == b'banco corrompido de proposito'}",
            corr.returncode == 0 and json.loads(corr.stdout).get("released")
            and db.read_bytes() == b"banco corrompido de proposito")
    db.unlink()
    aus = kit_cli(root, ["backup", "restaurar", "--origem", snap, "--destino", W / "restaurado-ausente",
                         "--retiradas", log], "titular")
    c.check("com o banco de origem ausente, a CLI restaura e não cria banco na origem", "código 0; origem sem banco",
            f"{aus.returncode}; banco criado={db.exists()}", aus.returncode == 0 and not db.exists())
    bk = run([PY, "-B", SCRIPTS / "backup_sqlite.py", "--origem", W / "nao-existe.sqlite", "--destino", W / "ref.sqlite"])
    c.check("backup_sqlite com origem inexistente falha sem criar arquivos", "código 1; nada criado",
            f"{bk.returncode}; origem criada={(W / 'nao-existe.sqlite').exists()}",
            bk.returncode == 1 and not (W / "nao-existe.sqlite").exists() and not (W / "ref.sqlite").exists())
    # '#' no caminho (ex.: "Processo #12"): a URI precisa codificar o caractere (RG-1 e RG-2).
    import sqlite3 as _sq
    origem = W / "Processo #12" / "app.sqlite"
    origem.parent.mkdir(parents=True)
    _db = _sq.connect(str(origem))
    _db.execute("CREATE TABLE t (x)")
    _db.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(5)])
    _db.commit()
    _db.close()
    cerq = run([PY, "-B", SCRIPTS / "backup_sqlite.py", "--origem", origem, "--destino", W / "Processo #12" / "ref.sqlite"])
    dados = json.loads(cerq.stdout) if cerq.stdout.strip().startswith("{") else {}
    c.check("backup_sqlite com '#' no caminho copia os dados de verdade", "código 0; cópia com t=5; nenhum arquivo solto",
            f"{cerq.returncode}; {(dados.get('copia') or {}).get('tabelas')}; solto={(W / 'Processo').exists()}",
            cerq.returncode == 0 and (dados.get("copia") or {}).get("tabelas") == {"t": 5}
            and not (W / "Processo").exists())
    snap_c = W / "copia #3" / "snap"
    criar_c = kit_cli(W / "restaurado", ["backup", "criar", "--destino", snap_c], "titular")
    ver_c = kit_cli(W / "restaurado", ["backup", "verificar", "--origem", snap_c], "titular")
    rest_c = kit_cli(W / "restaurado", ["backup", "restaurar", "--origem", snap_c, "--destino", W / "restaurado #4",
                                        "--retiradas", W / "restaurado" / "state" / "retiradas.jsonl"], "titular")
    c.check("cópia em pasta com '#' é criada, verificada e restaurada pela CLI", "códigos 0, 0, 0; released=true",
            f"{criar_c.returncode}, {ver_c.returncode}, {rest_c.returncode}",
            criar_c.returncode == 0 and ver_c.returncode == 0 and rest_c.returncode == 0
            and json.loads(rest_c.stdout).get("released") is True and not (W / "copia").exists())
    return c


def cen10(W: Path) -> Cenario:
    c = Cenario("CEN-10", "CAG: preparo e reutilização do estado KV (modelo sintético)",
                "real-local com modelo sintético (mecanismo; qualidade não avaliada)", "R26 R27 R28")
    try:
        import importlib.util
        if importlib.util.find_spec("torch") is None or importlib.util.find_spec("transformers") is None:
            c.bloquear("torch e transformers ausentes (dependências opcionais): cenário não executável aqui")
            return c
    except Exception as exc:  # noqa: BLE001
        c.check("dependências do CAG", "importáveis", str(exc), False)
        return c
    corpus = []
    for nome, texto in (("GUIA-001.md", "A solicitação de proposta exige objeto, escopo e prazo.\nToda minuta recebe revisão humana antes da entrega."),
                        ("GUIA-003.md", "O relatório interno é enviado na quinta-feira.")):
        p = W / nome
        p.write_text(texto, encoding="utf-8")
        corpus.append(p)
    saida = W / "cag.json"
    r = run([PY, "-B", SCRIPTS / "cag_kv_demo.py", "--modelo-sintetico", "--corpus", *corpus,
             "--pergunta", "Quais campos compõem a proposta?", "--pergunta", "Quem revisa a minuta?",
             "--pergunta", "Em que dia sai o relatório?", "--testar-invalidacao", "--saida", saida])
    d = json.loads(saida.read_text(encoding="utf-8"))
    rows = d["perguntas"]
    c.check("prefill único com tamanho de KV = fórmula do livro", d["estimativa_kv_bytes_formula_livro"],
            d["cache_base_bytes_observado"], d["cache_base_bytes_observado"] == d["estimativa_kv_bytes_formula_livro"])
    c.check("prefixo não recalculado: ramo KV = cache-base + pergunta + gerados − 1", "True em todas",
            [(x["ramo_kv_tokens_final"], d["cache_base_tokens"], x["prefixo_reaproveitado"]) for x in rows],
            all(x["prefixo_reaproveitado"] for x in rows))
    c.check("ramo KV usado e cache-base restaurado a cada pergunta", "True em todas",
            [(x["ramo_kv_usado"], x["cache_base_intacto"]) for x in rows],
            all(x["ramo_kv_usado"] and x["cache_base_intacto"] for x in rows))
    c.check("saídas quente × frio idênticas (decodificação gulosa)", "True em todas",
            [x["saidas_identicas_quente_frio"] for x in rows], all(x["saidas_identicas_quente_frio"] for x in rows))
    c.check("cache antigo recusado após mudança do corpus", True, d["invalidacao"]["cache_antigo_recusado"],
            d["invalidacao"]["cache_antigo_recusado"] and r.returncode == 0)
    c.check("rótulo honesto: qualidade não avaliada", False, d["qualidade_avaliada"], d["qualidade_avaliada"] is False)
    return c


def _skill_creator_validator() -> Path | None:
    """skill-creator do perfil: plugin oficial do Claude Code (cache de plugins) ou o do aplicativo; o mais recente."""
    padroes = ((Path.home() / ".claude" / "plugins" / "cache", "claude-plugins-official/skill-creator/*/skills/skill-creator"),
               (Path.home() / "AppData" / "Local" / "Packages",
                "Claude_*/LocalCache/Roaming/Claude/local-agent-mode-sessions/skills-plugin/*/*/skills/skill-creator"))
    achados = [b for raiz, padrao in padroes for b in raiz.glob(padrao) if (b / "scripts" / "quick_validate.py").exists()]
    return max(achados, key=lambda b: (b / "scripts" / "quick_validate.py").stat().st_mtime) if achados else None


def cen11(W: Path) -> Cenario:
    c = Cenario("CEN-11", "Estrutura, metadados e limites da skill", "estrutural", "R35 (formato) + auditoria")
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    import yaml  # disponível neste ambiente; usado só na validação
    fm = yaml.safe_load(m.group(1))
    # Nome canônico, não o nome da pasta onde a cópia está (uma cópia em `arvore/` não é defeito; AF-05).
    c.check("nome kebab-case igual ao canônico fundacao-ia-multiprojetos", "fundacao-ia-multiprojetos", fm["name"],
            fm["name"] == "fundacao-ia-multiprojetos" and bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", fm["name"])),
            f"pasta: {SKILL.name}")
    d = fm["description"]
    c.check("descrição ≤ 1024 caracteres e sem < >", "≤1024", len(d), len(d) <= 1024 and "<" not in d and ">" not in d)
    # Lista do validador do catálogo Chat/Work, mais estrita que a especificação (que aceita `compatibility`
    # na raiz): `compatibility` fica dentro de `metadata` (relatório técnico da 1.4.0, PRM-02).
    meta = fm.get("metadata") or {}
    c.check("chaves de cabeçalho aceitas pelo padrão e pelo validador do Chat/Work",
            "name, description, license, metadata (compatibility dentro de metadata, até 500 caracteres)",
            sorted(fm), set(fm) <= {"name", "description", "license", "allowed-tools", "metadata"}
            and isinstance(meta.get("compatibility"), str) and 0 < len(meta["compatibility"]) <= 500)
    c.check("metadata como mapa de textos", "todos str", {k: type(v).__name__ for k, v in fm["metadata"].items()},
            all(isinstance(v, str) for v in fm["metadata"].values()))
    linhas = text.count("\n")
    c.check("SKILL.md enxuto (< 500 linhas)", "< 500", linhas, linhas < 500)
    outros = [p for p in SKILL.rglob("SKILL.md") if p != SKILL / "SKILL.md" and "evals" not in p.relative_to(SKILL).parts[:1]]
    c.check("um único SKILL.md no pacote", 0, [str(p) for p in outros], not outros)
    pyc = [str(p) for p in SKILL.rglob("__pycache__")]
    c.check("sem artefatos de compilação na skill", 0, pyc, not pyc)
    sc = _skill_creator_validator()
    if sc:
        r = run([PY, "-B", "-m", "scripts.quick_validate", SKILL], cwd=sc)
        c.check("quick_validate do skill-creator", "Skill is valid!", r.stdout.strip(), r.returncode == 0)
    else:
        c.pulada("quick_validate do skill-creator", "validador não encontrado no perfil (Path.home()); rode-o à parte")
    scan = Path.home() / ".claude" / "skills" / "book-to-skill" / "tools" / "scan_generated_skill.py"
    if not scan.exists():
        c.pulada("varredura de injeção do book-to-skill sobre todos os Markdown", "book-to-skill não instalado no perfil (Path.home())")
    if scan.exists():
        # O verificador do book-to-skill só examina SKILL.md e chapters/: o espelho põe TODOS os
        # Markdown da skill em chapters/ para que nenhum fique fora da varredura.
        espelho = W / "espelho-varredura" / SKILL.name
        (espelho / "chapters").mkdir(parents=True)
        shutil.copy2(SKILL / "SKILL.md", espelho / "SKILL.md")
        mds = [p for p in SKILL.rglob("*.md") if p.name != "SKILL.md" and "evals" not in p.relative_to(SKILL).parts[:1]]
        for p in mds:
            nome = p.relative_to(SKILL).as_posix().replace("/", "__")
            shutil.copy2(p, espelho / "chapters" / nome)
        r = run([PY, "-B", scan, espelho])
        saida = (r.stdout + r.stderr)
        achados = re.findall(r"^\s*(?:WARN|ERROR)\s+chapters/(\S+?):(\d+)\s+\[([^\]]+)\]", saida, re.M)
        # Achados revisados em contexto (a regra do verificador é ampla de propósito):
        revisados = {("references/capacidades/08-ferramentas-hooks-mcp-skills-plugins.md", "tool.exfiltration_shape"):
                     "exemplos de regras deny para .env/segredos e limite de Bash(curl): conteúdo defensivo"}
        nao_revisados = [(n.replace("__", "/"), l, regra) for n, l, regra in achados
                         if (n.replace("__", "/"), regra) not in revisados]
        c.check("varredura de injeção do book-to-skill sobre todos os Markdown; achados revisados em contexto",
                f"{len(mds) + 1} arquivos; nenhum SKIP; 0 achados não revisados",
                f"achados={[(n.replace('__', '/'), l, regra) for n, l, regra in achados]}; não revisados={nao_revisados}",
                "SKIP" not in saida and not nao_revisados and ("passed" in saida or bool(achados)),
                f"arquivos: {len(mds) + 1}; revisados: {list(revisados.values())}")
    return c


def cen12(W: Path) -> Cenario:
    c = Cenario("CEN-12", "Conformidade do kit em instalação limpa", "real-local", "R03 R42 R58 R59")
    root = W / "f12"
    run([PY, "-B", SCRIPTS / "instalar_kit.py", "--destino", root])
    r = run([PY, "-B", "-m", "unittest", "discover", "-s", "tests"], cwd=root, timeout=900)
    m = re.search(r"Ran (\d+) tests", r.stderr)
    c.check("suíte de conformidade passa", "OK", r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "",
            r.returncode == 0 and "OK" in r.stderr, f"testes: {m.group(1) if m else '?'}")
    return c


def _matcher_documentado() -> str:
    texto = (SKILL / "references" / "capacidades" / "08-ferramentas-hooks-mcp-skills-plugins.md").read_text(encoding="utf-8")
    m = re.search(r'"PreToolUse": \[\{"matcher": "([^"]+)"', texto)
    return m.group(1) if m else ""


def cen13(W: Path) -> Cenario:
    c = Cenario("CEN-13", "Hooks preventivos: escrita fora do projeto e troca de identidade negadas",
                "real-local (eventos simulados do host)", "R33 R52 + identidade")
    hook = SKILL / "assets" / "hooks" / "guarda_caminho.py"
    hook_id = SKILL / "assets" / "hooks" / "guarda_identidade.py"
    raiz = W / "fund"
    (raiz / "projects" / "juridico-lab").mkdir(parents=True)
    env = {**BASE_ENV, "FUNDACAO_PROJECT": "juridico-lab", "FUNDACAO_RAIZ": str(raiz)}

    def decide(evento, e=env, h=hook, bruto=None):
        r = run([PY, "-B", h], env=e, stdin=bruto if bruto is not None else json.dumps(evento))
        return json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] if r.stdout.strip() else "sem_decisao"
    dentro = str(raiz / "projects" / "juridico-lab" / "minuta.md")
    c.check("escrita dentro do projeto autenticado segue o fluxo normal", "sem_decisao",
            decide({"tool_name": "Write", "tool_input": {"file_path": dentro}}),
            decide({"tool_name": "Write", "tool_input": {"file_path": dentro}}) == "sem_decisao")
    proibidas = [
        {"tool_name": "Write", "tool_input": {"file_path": str(raiz / "projects" / "reversa-lab" / "x.md")}},
        {"tool_name": "Edit", "tool_input": {"file_path": str(raiz / "projects" / "juridico-lab" / ".." / "reversa-lab" / "y.md")}},
        {"tool_name": "Write", "tool_input": {"file_path": str(raiz / "registry" / "components" / "x.json")}},
        {"tool_name": "NotebookEdit", "tool_input": {"notebook_path": str(W / "fora.ipynb")}},
        {"tool_name": "MultiEdit", "tool_input": {"file_path": str(W / "fora.md")}},
        {"tool_name": "mcp__docs__escrever", "tool_input": {"path": "x"}},
        {"tool_name": "Write", "tool_input": {"file_path": "../../fora.md"}, "cwd": str(raiz / "projects" / "juridico-lab")},
        {"tool_name": "Edit", "tool_input": {"file_path": str(raiz / "state" / "state.sqlite")}},
        {"tool_name": "Write", "tool_input": {}},
        {"tool_name": "Write", "tool_input": {"file_path": str(Path.home() / ".claude" / "settings.json")}},
    ]
    negadas = sum(1 for ev in proibidas if decide(ev) == "deny")
    c.check("0 em 10 tentativas indevidas passam (Write, Edit, '..', MCP, NotebookEdit)", "10 negadas", negadas, negadas == 10)
    matcher = _matcher_documentado()
    nomes = sorted({ev["tool_name"] for ev in proibidas})
    roteadas = [n for n in nomes if re.fullmatch(matcher, n)] if matcher else []
    c.check("o matcher documentado encaminha ao hook todas as ferramentas testadas (inclusive MCP)",
            f"{len(nomes)} de {len(nomes)}", f"matcher={matcher!r}; {len(roteadas)} de {len(nomes)}",
            bool(matcher) and roteadas == nomes)
    sem_proj = {k: v for k, v in env.items() if k != "FUNDACAO_PROJECT"}
    c.check("sem projeto autenticado: falha fechada", "deny",
            decide({"tool_name": "Write", "tool_input": {"file_path": dentro}}, sem_proj),
            decide({"tool_name": "Write", "tool_input": {"file_path": dentro}}, sem_proj) == "deny")
    c.check("evento malformado: falha fechada", "deny", decide(None, bruto="isto não é JSON"),
            decide(None, bruto="isto não é JSON") == "deny" and decide(None, bruto="[1, 2]") == "deny")
    c.check("leitura de arquivo não é bloqueada por este hook", "sem_decisao",
            decide({"tool_name": "Read", "tool_input": {"file_path": dentro}}),
            decide({"tool_name": "Read", "tool_input": {"file_path": dentro}}) == "sem_decisao")
    trocas = ["FUNDACAO_PRINCIPAL=titular python -m fundacao status",
              "export FUNDACAO_PRINCIPAL=titular", "set FUNDACAO_PRINCIPAL=titular && python -m fundacao status",
              "$env:FUNDACAO_PRINCIPAL='titular'; python -m fundacao status",
              "[Environment]::SetEnvironmentVariable('FUNDACAO_PRINCIPAL','titular')"]
    negadas_id = [t for t in trocas if decide({"tool_name": "Bash" if "$env" not in t else "PowerShell",
                                               "tool_input": {"command": t}}, h=hook_id) == "deny"]
    c.check("troca de identidade pela sessão é negada (bash, cmd, PowerShell)", f"{len(trocas)} negadas",
            len(negadas_id), len(negadas_id) == len(trocas))
    normal = decide({"tool_name": "Bash", "tool_input": {"command": "python -m fundacao status"}}, h=hook_id)
    liberado = decide({"tool_name": "Bash", "tool_input": {"command": trocas[0]}},
                      e={**env, "FUNDACAO_PERMITIR_TROCA_IDENTIDADE": "1"}, h=hook_id)
    c.check("comando comum segue; laboratório pode liberar a troca explicitamente", "sem_decisao; sem_decisao",
            f"{normal}; {liberado}", normal == "sem_decisao" and liberado == "sem_decisao")
    # Console legado (sem PYTHONUTF8): a saída é JSON só com ASCII; nome fora do cp1252 ainda nega.
    legado = {k: v for k, v in env.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    ev_u = json.dumps({"tool_name": "mcp__srv__ferramenta_\u2603", "tool_input": {}})
    r_u = run([PY, "-B", hook], env=legado, stdin=ev_u)
    r_i = run([PY, "-B", hook_id], env=legado, stdin=json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": "export FUNDACAO_PRINCIPAL=titular # \u2603"}}))
    dec = [json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] if r.stdout.strip().isascii()
           and r.stdout.strip() else "?" for r in (r_u, r_i)]
    c.check("sem PYTHONUTF8 (página de código legada), a saída segue válida e a negativa vale", "códigos 0; deny, deny",
            f"{r_u.returncode}, {r_i.returncode}; {dec}", r_u.returncode == 0 and r_i.returncode == 0 and dec == ["deny", "deny"])
    contorno = decide({"tool_name": "Bash", "tool_input": {"command":
                       "python -c \"import os; os.environ['FUNDACAO_' + 'PRINCIPAL'] = 'titular'\""}}, h=hook_id)
    c.check("limite declarado confirmado: nome montado em tempo de execução passa pelo hook de identidade",
            "sem_decisao (guarda-corpo, não barreira)", contorno, contorno == "sem_decisao")
    # AF-07: ler a variável não é troca de identidade; outras formas de atribuição no PowerShell são negadas.
    leitura = decide({"tool_name": "PowerShell", "tool_input": {"command": "echo $env:FUNDACAO_PRINCIPAL"}}, h=hook_id)
    outras = ["Set-Item env:FUNDACAO_PRINCIPAL 'titular'", "${env:FUNDACAO_PRINCIPAL} = 'titular'",
              "Set-Item -Path env:FUNDACAO_PRINCIPAL -Value titular", "Remove-Item env:FUNDACAO_PRINCIPAL"]
    negadas_ps = [t for t in outras if decide({"tool_name": "PowerShell", "tool_input": {"command": t}}, h=hook_id) == "deny"]
    c.check("ler FUNDACAO_PRINCIPAL segue; Set-Item, ${env:...}= e Remove-Item são negados (AF-07)",
            f"sem_decisao; {len(outras)} negadas", f"{leitura}; {len(negadas_ps)} negadas",
            leitura == "sem_decisao" and len(negadas_ps) == len(outras))
    # CF-01 (conferência da 1.4.3): o padrão da 1.4.3 deixava passar formas comuns de atribuição explícita no
    # PowerShell — caminho `env:` entre aspas, `-Path:`/`-Path=`, `Env:\`, `Remove-Item` entre aspas, `+=` e
    # `New-Item -Path env: -Name` —, que a 1.4.2 negava; Get-ChildItem e `-eq` são leitura e seguem.
    formas_cf01 = ['Set-Item -Path "env:FUNDACAO_PRINCIPAL" -Value "titular"', "Set-Item 'env:FUNDACAO_PRINCIPAL' 'titular'",
                   "Set-Item -Path:env:FUNDACAO_PRINCIPAL -Value titular", "Set-Item -Path=env:FUNDACAO_PRINCIPAL -Value titular",
                   "Set-Item Env:\\FUNDACAO_PRINCIPAL titular", 'Remove-Item "env:FUNDACAO_PRINCIPAL"',
                   "$env:FUNDACAO_PRINCIPAL += 'x'", "New-Item -Path env: -Name FUNDACAO_PRINCIPAL -Value titular"]
    leituras_cf01 = ["Get-ChildItem env:FUNDACAO_PRINCIPAL", "if ($env:FUNDACAO_PRINCIPAL -eq 'titular') { 'ok' }"]
    negadas_cf = [t for t in formas_cf01 if decide({"tool_name": "PowerShell", "tool_input": {"command": t}}, h=hook_id) == "deny"]
    livres_cf = [t for t in leituras_cf01 if decide({"tool_name": "PowerShell", "tool_input": {"command": t}}, h=hook_id) == "sem_decisao"]
    c.check("aspas, -Path:/-Path=, Env:\\, Remove-Item entre aspas, += e New-Item -Name são negados; Get-ChildItem e -eq seguem (CF-01)",
            f"{len(formas_cf01)} negadas; {len(leituras_cf01)} livres", f"{len(negadas_cf)} negadas; {len(livres_cf)} livres",
            len(negadas_cf) == len(formas_cf01) and len(livres_cf) == len(leituras_cf01),
            f"passaram: {[t for t in formas_cf01 if t not in negadas_cf]}")
    # AF-08: padrões com `*` em FUNDACAO_MCP_PERMITIDAS liberam as ferramentas MCP do próprio host.
    e_mcp = {**env, "FUNDACAO_MCP_PERMITIDAS": "mcp__ccd_*,mcp__fundacao__buscar"}
    host_ok = decide({"tool_name": "mcp__ccd_turn__update_plan", "tool_input": {}}, e_mcp)
    exata_ok = decide({"tool_name": "mcp__fundacao__buscar", "tool_input": {}}, e_mcp)
    outra_neg = decide({"tool_name": "mcp__outra__gravar", "tool_input": {}}, e_mcp)
    c.check("padrão mcp__ccd_* libera as ferramentas do host; nome exato libera; outra MCP continua negada (AF-08)",
            "sem_decisao; sem_decisao; deny", f"{host_ok}; {exata_ok}; {outra_neg}",
            host_ok == "sem_decisao" and exata_ok == "sem_decisao" and outra_neg == "deny")
    return c


def cen14(W: Path) -> Cenario:
    c = Cenario("CEN-14", "Matriz de requisitos: estados honestos aplicados", "estrutural", "R43 R50 + Ap. B")
    mat = W / "requisitos.csv"
    run([PY, "-B", SCRIPTS / "matriz.py", "init", "--saida", mat])
    ok = run([PY, "-B", SCRIPTS / "matriz.py", "validar", "--matriz", mat])
    c.check("matriz inicial válida (60 linhas em desenvolvimento)", "ok", ok.stdout.strip()[-80:], ok.returncode == 0)
    import csv
    rows = list(csv.DictReader(mat.open(encoding="utf-8", newline="")))
    by = {r["id"]: r for r in rows}
    by["R12"].update(estado="implementado_ativo", nivel_evidencia="executado", simulado="sim",
                     caminho_evidencia="evidence/A08", versao_avaliada="kit 1.0.0")
    by["R33"].update(estado="implementado_inativo", nivel_evidencia="executado", caminho_evidencia="evidence/A11B",
                     versao_avaliada="1")
    by["R34"].update(estado="bloqueado", bloqueio="pacote ausente", condicao_resolucao="autorizar instalação")
    by["R01"].update(estado="concluido_com_ressalvas")
    rows = [r for r in rows if r["id"] not in ("R05", "R57")]
    with mat.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    bad = run([PY, "-B", SCRIPTS / "matriz.py", "validar", "--matriz", mat])
    erros = json.loads(bad.stdout)["erros"]
    esperados = {"R12": "simulação", "R33": "demonstracao_anterior", "R34": "impacto", "R01": "estado inválido",
                 "R05": "ausente", "R57": "proposta 3.0"}
    achados = {k: any(e.startswith(k) and v in e for e in erros) for k, v in esperados.items()}
    c.check("violações detectadas (simulação, inativo sem demonstração, bloqueio sem impacto, estado inventado, "
            "id do livro e id da 3.0 removidos)", "todas", achados, bad.returncode == 1 and all(achados.values()))
    rel = json.loads(run([PY, "-B", SCRIPTS / "matriz.py", "relatorio", "--matriz", mat]).stdout)
    c.check("relatório começa pelos bloqueados (ordem da A36)", "R34 primeiro", rel["linhas"][0]["id"],
            rel["linhas"][0]["id"] == "R34")
    return c


def cen15(W: Path) -> Cenario:
    c = Cenario("CEN-15", "MCP local: descoberta, chamada autorizada, negativa entre projetos e encerramento",
                "real-local (SDK mcp, processo separado por stdio; sem rede)", "R34")
    import importlib.util
    if importlib.util.find_spec("mcp") is None:
        c.bloquear("SDK mcp ausente (dependência opcional; instalar exige autorização)")
        return c
    root = W / "fundacao-cen15"
    con, adm, sim = nova_fundacao_api(root)
    con.close()
    descarregar_modulos_fundacao()
    (root / "projects" / "juridico-lab" / "data" / "catalog.json").write_text(json.dumps({"doc-aurora-01": "a.md"}), encoding="utf-8")
    (root / "projects" / "reversa-lab" / "data" / "catalog.json").write_text(json.dumps({"doc-eng-segredo-fic": "b.md"}), encoding="utf-8")
    saida = W / "mcp.json"
    env = {**BASE_ENV, "FUNDACAO_PRINCIPAL": "operador-juridico"}
    r = run([PY, "-B", SCRIPTS / "mcp_ensaio.py", "--raiz", root, "--projeto", "juridico-lab", "--outro", "reversa-lab",
             "--saida", saida], env=env, timeout=180)
    d = json.loads(saida.read_text(encoding="utf-8")) if saida.exists() else {}
    c.check("descoberta das ferramentas do servidor da fundação", "listar_projetos, listar_documentos, buscar",
            d.get("ferramentas"), set(d.get("ferramentas") or []) >= {"listar_projetos", "listar_documentos", "buscar"})
    c.check("chamada autorizada devolve só o próprio projeto", "['doc-aurora-01']",
            (d.get("chamada_autorizada") or {}).get("documentos"),
            (d.get("chamada_autorizada") or {}).get("documentos") == ["doc-aurora-01"])
    neg = d.get("negativa_outro_projeto") or {}
    c.check("negativa entre projetos sem conteúdo alheio", "erro com 'acesso negado'; sem 'doc-eng-segredo-fic'",
            neg.get("mensagem"), neg.get("erro") is True and "acesso negado" in neg.get("mensagem", "")
            and "doc-eng-segredo-fic" not in json.dumps(d))
    import sqlite3
    db = sqlite3.connect(str(root / "state" / "state.sqlite"))
    n = db.execute("SELECT COUNT(*) FROM event WHERE kind='access_denied' AND subject='operador-juridico'").fetchone()[0]
    db.close()
    c.check("negativa registrada na trilha da fundação", ">= 1", n, n >= 1)
    c.check("sessão encerrada e ensaio concluído", "código 0; encerrado", f"{r.returncode}; {d.get('encerrado')}",
            r.returncode == 0 and d.get("encerrado") is True)
    c.check("versão de protocolo negociada e servidor identificados", "protocolo presente; servidor da fundação",
            f"{d.get('protocolo_negociado')}; {d.get('servidor')}",
            bool(d.get("protocolo_negociado")) and (d.get("servidor") or {}).get("nome") == "fundacao-ia-multiprojetos")
    return c


def cen16(W: Path) -> Cenario:
    c = Cenario("CEN-16", "Atualização do kit numa fundação existente (conflito, substituição com retorno)",
                "real-local", "R46 R47 + C6")
    root = W / "f16"
    run([PY, "-B", SCRIPTS / "instalar_kit.py", "--destino", root])
    init = root / "fundacao" / "__init__.py"
    atual = init.read_text(encoding="utf-8")
    antigo = re.sub(r'KIT_VERSION = "[^"]+"', 'KIT_VERSION = "0.9.0"', atual)
    init.write_text(antigo, encoding="utf-8")  # instância "antiga"
    p1 = run([PY, "-B", SCRIPTS / "instalar_kit.py", "--destino", root])
    r1 = json.loads(p1.stdout)
    c.check("sem --atualizar: nada é escrito, a diferença fica preservada e a saída não é sucesso (F15)",
            "código 3; conflito em fundacao/__init__.py; nada escrito; versão declarada nula; no destino 0.9.0",
            f"{p1.returncode}; {r1['conflitos_preservados']}; {r1.get('nada_escrito')}; {r1['kit_version']}; "
            f"{r1.get('versao_no_destino')}",
            p1.returncode == 3 and r1["conflitos_preservados"] == ["fundacao/__init__.py"]
            and r1.get("nada_escrito") is True and r1["kit_version"] is None
            and r1.get("versao_no_destino") == "0.9.0" and r1["atualizacao_incompleta"] is True)
    r2 = json.loads(run([PY, "-B", SCRIPTS / "instalar_kit.py", "--destino", root, "--atualizar"]).stdout)
    guardado = Path(r2["backup_dos_substituidos"] or ".") / "fundacao" / "__init__.py"
    c.check("com --atualizar: substitui, guarda a versão anterior e registra a versão instalada",
            "substituído; cópia anterior guardada; versão = a do kit",
            f"{[s['path'] for s in r2['substituidos']]}; guardado={guardado.exists()}; {r2['kit_version']}",
            [s["path"] for s in r2["substituidos"]] == ["fundacao/__init__.py"] and guardado.exists()
            and guardado.read_text(encoding="utf-8") == antigo and r2["kit_version"] == r2["kit_origem"])
    r3 = json.loads(run([PY, "-B", SCRIPTS / "instalar_kit.py", "--destino", root]).stdout)
    c.check("reexecução depois da atualização não muda nada", "0 copiados, 0 conflitos, 0 substituídos",
            f"{len(r3['copiados'])}, {len(r3['conflitos_preservados'])}, {len(r3['substituidos'])}",
            not r3["copiados"] and not r3["conflitos_preservados"] and not r3["substituidos"])
    # Fundação de kit anterior: registro de retiradas vazio e sem identidade (como o `init` da 1.2.0).
    kit_cli(root, ["init", "--admin", "titular"])
    (root / "state" / "retiradas.jsonl").write_text("", encoding="utf-8")
    recusa = kit_cli(root, ["backup", "criar", "--destino", W / "bk-antes"], "titular")
    ini = kit_cli(root, ["init"])
    depois = kit_cli(root, ["backup", "criar", "--destino", W / "bk-depois"], "titular")
    c.check("depois de atualizar, o backup pede `init`; com ele, o registro ganha identidade e o backup volta",
            "código 2 'rode `init`'; init 0; backup 0 com a identidade anotada",
            f"{recusa.returncode}; {ini.returncode}; {depois.returncode}",
            recusa.returncode == 2 and "init" in recusa.stderr and ini.returncode == 0 and depois.returncode == 0
            and json.loads(depois.stdout)["retiradas"]["log_id"]
            == json.loads(ini.stdout)["registro_retiradas"]["identidade"])
    return c


CENARIOS = {"CEN-01": cen01, "CEN-02": cen02, "CEN-03": cen03, "CEN-04": cen04, "CEN-05": cen05, "CEN-06": cen06,
            "CEN-07": cen07, "CEN-08": cen08, "CEN-09": cen09, "CEN-10": cen10, "CEN-11": cen11, "CEN-12": cen12,
            "CEN-13": cen13, "CEN-14": cen14, "CEN-15": cen15, "CEN-16": cen16}


def _contagem(verificacoes: list[dict]) -> str:
    """`aprovadas/executadas` e, se houver, quantas foram puladas neste ambiente (visíveis, não contadas)."""
    puladas = sum(1 for c in verificacoes if c.get("pulada"))
    ok = sum(1 for c in verificacoes if c["passou"])
    base = f"{ok}/{len(verificacoes) - puladas}"
    return f"{base}, {puladas} pulada(s)" if puladas else base


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--saida", type=Path, required=True)
    ap.add_argument("--manter", action="store_true", help="não apaga as pastas temporárias")
    ap.add_argument("--so", help="lista de cenários, ex.: CEN-01,CEN-07")
    ap.add_argument("--opcionais-ausentes-bloqueiam", action="store_true",
                    help="cenário bloqueado por dependência opcional ausente não reprova (só a CI pública)")
    args = ap.parse_args()
    escolha = [x.strip() for x in args.so.split(",")] if args.so else list(CENARIOS)
    base = Path(tempfile.mkdtemp(prefix="fundacao-cen-"))
    resultados = []
    for cid in escolha:
        W = base / cid
        W.mkdir()
        t0 = time.time()
        try:
            cen = CENARIOS[cid](W)
        except Exception as exc:  # noqa: BLE001
            cen = Cenario(cid, CENARIOS[cid].__name__, "?", "?")
            cen.erro = f"{type(exc).__name__}: {exc}"
            descarregar_modulos_fundacao()
        d = cen.as_dict()
        d["duracao_s"] = round(time.time() - t0, 2)
        resultados.append(d)
        print(f"{cid}: {situacao(d)} ({_contagem(d['verificacoes'])}) {d['erro'] or d['bloqueado'] or ''}", flush=True)
    args.saida.mkdir(parents=True, exist_ok=True)
    meta = {"executado_em": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "python": sys.version.split()[0],
            "plataforma": sys.platform, "pasta_temporaria": str(base), "mantida": args.manter}
    (args.saida / "resultados.json").write_text(json.dumps({"meta": meta, "cenarios": resultados},
                                                           ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    md = ["# Resultados dos cenários executáveis", "",
          f"Executado em {meta['executado_em']} · Python {meta['python']} · {meta['plataforma']}", "",
          "| Cenário | Tipo | Requisitos | Verificações | Resultado |", "|---|---|---|---|---|"]
    for r in resultados:
        md.append(f"| {r['id']} {r['nome']} | {r['tipo']} | {r['requisitos']} | {_contagem(r['verificacoes'])} | "
                  f"{situacao(r)} |")
    md += ["", "## Detalhes", ""]
    for r in resultados:
        md.append(f"### {r['id']} — {r['nome']}")
        if r["erro"]:
            md.append(f"Erro: `{r['erro']}`")
        if r["bloqueado"]:
            md.append(f"Bloqueado: {r['bloqueado']}")
        for c in r["verificacoes"]:
            marca = "-" if c.get("pulada") else ("x" if c["passou"] else " ")
            md.append(f"- [{marca}] {c['verificacao']} — esperado: {c['esperado']}; "
                      f"observado: {c['observado']}" + (f" ({c['evidencia']})" if c["evidencia"] else ""))
        md.append("")
    (args.saida / "RESULTADOS.md").write_text("\n".join(md), encoding="utf-8", newline="\n")
    if not args.manter:
        shutil.rmtree(base, ignore_errors=True)
    return codigo_de_saida(resultados, args.opcionais_ausentes_bloqueiam)


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
