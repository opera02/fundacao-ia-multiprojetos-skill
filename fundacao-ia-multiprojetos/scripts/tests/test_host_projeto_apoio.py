"""Apoio aos testes do HOST da 1.7.10 (pastas descartáveis; só biblioteca padrão; nada da raiz real).

`skill_de_ensaio` monta uma cópia da skill só com o que o preparo do host usa (assets/host, assets/hooks, o kit e os
scripts da regra única, da cópia conferida e da gravação sem ligação) e põe substitutos de ensaio nas peças que são de
outros pacotes do lote 2: os hooks novos (pacote HOOKS) só se faltarem; o porteiro (PORTEIRO), o `aberturas.vigente`
do kit (ABERTURAS) e a ferramenta do titular sempre, para o ensaio ser determinístico (os pacotes donos testam as
peças reais; `porteiro_real=True` mantém o porteiro da skill, para o teste de integração). `raiz_de_ensaio` monta a
raiz como o preparo do Windows a deixa: hooks e kit iguais aos da skill. `relatorio_de_canario` e `instalar_canario`
dão ao ensaio o relatório aprovado do canário (o formato do pacote CANARIO), sem o qual nenhuma ficha vale.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from apoio import ENV, SKILL

TODOS_OS_HOOKS = ("guarda_caminho.py", "guarda_identidade.py", "sinais_sessao.py", "guarda_ferramentas.py",
                  "guarda_rede.py", "guarda_leitura.py", "aviso_copia.py", "regras_codigo.py")
LINUX = os.name == "posix" and sys.platform.startswith("linux")
PYTHON_LINUX = "/usr/bin/python3"
PORTEIRO_DA_SKILL = SKILL / "assets" / "host" / "wsl" / "porteiro.py"

PORTEIRO_FALSO = '''#!/usr/bin/env python3
"""Porteiro de ensaio: registra a chamada (sem conteúdo; do ambiente, os nomes e o valor de WSL_DISTRO_NAME, que a
emenda E1 dos contratos manda o lançador passar); em conferir, compara o kit_sha256 do porteiro.json com a conta do kit
(`sha256_do_kit`: a receita documentada do pacote PORTEIRO, linhas "<sha256>  <caminho>" em ordem dos bytes do
caminho, só __pycache__ de fora); em servir, espera o lançador morrer ou o SIGTERM. Importável: o preparo do host
carrega daqui a conta do kit, como fará do porteiro real."""
import hashlib, json, os, signal, sys, time
REGISTRO = {registro!r}


def sha256_do_kit(raiz):
    base = os.path.join(str(raiz), "fundacao")
    if os.path.islink(base) or not os.path.isdir(base):
        raise OSError("kit ausente ou ligação: " + base)
    itens = []
    for atual, pastas, arquivos in os.walk(base):
        pastas[:] = [p for p in pastas if p != "__pycache__"]
        for nome in arquivos:
            caminho = os.path.join(atual, nome)
            rel = os.path.relpath(caminho, base).replace(os.sep, "/")
            with open(caminho, "rb") as f:
                itens.append((rel.encode("utf-8"), hashlib.sha256(f.read()).hexdigest() + "  " + rel + "\\n"))
    return hashlib.sha256("".join(l for _, l in sorted(itens)).encode("utf-8")).hexdigest()


def principal(args):
    with open(REGISTRO, "a", encoding="utf-8") as f:
        f.write(json.dumps({{"argv": args, "cwd": os.getcwd(), "env": sorted(os.environ),
                            "distro": os.environ.get("WSL_DISTRO_NAME")}}) + "\\n")
    if args[:1] == ["conferir"]:
        controle = REGISTRO + ".conferir"
        if os.path.exists(controle):
            return int(open(controle).read())
        with open(args[args.index("--config") + 1], encoding="utf-8") as f:
            cfg = json.load(f)
        return 0 if sha256_do_kit(cfg["raiz"]) == cfg["kit_sha256"] else 2
    if args[:1] == ["servir"]:
        fila = args[args.index("--fila") + 1]
        pid = int(args[args.index("--pid-lancador") + 1])
        for pasta in ("pedidos", "respostas"):
            os.makedirs(os.path.join(fila, pasta), exist_ok=True)
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        while True:
            try:
                os.kill(pid, 0)
            except OSError:
                return 0
            time.sleep(0.1)
    return 2


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
'''

ABERTURAS_FALSO = '''"""aberturas.vigente de ensaio: a ficha de maior versão da área, sem conferir a assinatura (o kit real confere)."""
import hashlib, json, os, re
from pathlib import Path


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def vigente(raiz, projeto, area):
    area = Path(area)
    base = {"projeto": projeto, "valida": False, "versao": None, "arquivo": None, "sha256": None,
            "sig_sha256": None, "ficha": None, "motivo_invalida": "sem ficha", "area": str(area)}
    nomes = os.listdir(area) if area.is_dir() else []
    fichas = sorted((int(m.group(1)), n) for n in nomes if (m := re.fullmatch(r"ficha-v([0-9]+)[.]json", n)))
    if not fichas:
        return base
    versao, nome = fichas[-1]
    arquivo, sig = area / nome, area / (nome + ".sig")
    if not sig.is_file():
        return {**base, "motivo_invalida": "sem assinatura"}
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    return {**base, "valida": True, "versao": versao, "arquivo": str(arquivo), "sha256": _sha(arquivo),
            "sig_sha256": _sha(sig), "ficha": dados, "motivo_invalida": None}


def conferir_assinatura(bruto, sig, ancora=None):
    """A de ensaio (1.7.10.1, aceite de risco): vale a assinatura de ensaio, que cita o SHA-256 dos bytes."""
    if sig == ("assinatura de ensaio " + hashlib.sha256(bruto).hexdigest() + "\\n").encode("ascii"):
        return {"ok": True, "motivo": "assinatura válida", "assinante": "titular", "impressao_digital": "SHA256:ensaio"}
    return {"ok": False, "motivo": "assinatura de ensaio não confere"}
'''

TITULAR_FALSO = '''"""Ferramenta do titular de ensaio: só registra os argumentos (a real assina com a chave do titular)."""
import json, sys
with open({registro!r}, "a", encoding="utf-8") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
'''

CLAUDE_FALSO = ("#!/usr/bin/env bash\n"
                'for a in "$@"; do echo "ARG:$a"; done > "$HOME/chamada-claude.txt"\n'
                'env | sort | sed "s/^/ENV:/" >> "$HOME/chamada-claude.txt"\n'
                'echo "PWD:$(pwd)" >> "$HOME/chamada-claude.txt"\n'
                'echo "TEMP_EXISTE:$([ -d "$TMPDIR" ] && stat -c %a "$TMPDIR")" >> "$HOME/chamada-claude.txt"\n'
                'echo "TEMP_CONTEUDO:$(ls -A "$TMPDIR" 2>/dev/null | wc -l)" >> "$HOME/chamada-claude.txt"\n'
                'if [ -e "$HOME/criar-marcador" ]; then : > .gitmodules; fi\n')


def carregar_preparo(skill: Path = SKILL):
    sys.dont_write_bytecode = True  # sem __pycache__ em assets/host/ (o CEN-11 acusa)
    spec = importlib.util.spec_from_file_location("preparo_host_1710_" + hashlib.sha256(str(skill).encode()).hexdigest()[:8],
                                                  Path(skill) / "assets" / "host" / "preparo_host.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def sha(caminho) -> str:
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


def _copiar(origem: Path, destino: Path) -> None:
    if origem.is_dir():
        shutil.copytree(origem, destino, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    else:
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origem, destino)


def porteiro_real_na_skill() -> bool:
    """A skill já tem o porteiro do pacote PORTEIRO (com a conta do kit), não um substituto."""
    if not PORTEIRO_DA_SKILL.is_file():
        return False
    texto = PORTEIRO_DA_SKILL.read_text(encoding="utf-8", errors="replace")
    return "def sha256_do_kit" in texto and "Porteiro de ensaio" not in texto


def skill_de_ensaio(base: Path, *, registro_porteiro: Path | None = None, registro_titular: Path | None = None,
                    porteiro_real: bool = False) -> Path:
    """Cópia de ensaio da skill (ver o módulo). Os substitutos sempre gravados: porteiro (salvo `porteiro_real`, com o
    porteiro do pacote PORTEIRO na skill), aberturas e titular."""
    skill = base / "skill-ensaio" / "fundacao-ia-multiprojetos"
    for rel in ("SKILL.md", "assets/host", "assets/hooks", "assets/fundacao-kit/fundacao", "scripts/regras_de_segredo.py",
                "scripts/copia_segura.py", "scripts/gravacao_segura.py", "scripts/instrucoes_aninhadas.py",
                "scripts/codigo_do_plano.py", "scripts/manifesto.py"):  # os três últimos: a conferência das aninhadas (A3)
        _copiar(SKILL / rel, skill / rel)
    for nome in TODOS_OS_HOOKS:
        alvo = skill / "assets" / "hooks" / nome
        if not alvo.exists():
            alvo.write_text("# substituto de ensaio do hook " + nome + " (pacote HOOKS)\nimport sys\nsys.exit(0)\n",
                            encoding="utf-8", newline="\n")
    registro_porteiro = registro_porteiro or (base / "porteiro-chamadas.jsonl")
    if not (porteiro_real and porteiro_real_na_skill()):
        (skill / "assets" / "host" / "wsl" / "porteiro.py").write_text(
            PORTEIRO_FALSO.format(registro=str(registro_porteiro)), encoding="utf-8", newline="\n")
    (skill / "assets" / "fundacao-kit" / "fundacao" / "core" / "aberturas.py").write_text(
        ABERTURAS_FALSO, encoding="utf-8", newline="\n")
    (skill / "assets" / "host" / "fundacao_titular.py").write_text(
        TITULAR_FALSO.format(registro=str(registro_titular or (base / "titular-chamadas.jsonl"))), encoding="utf-8",
        newline="\n")
    return skill


def raiz_de_ensaio(base: Path, skill: Path, projeto: str = "caso-real", outros=("lab-a",)) -> Path:
    """Raiz de fundação fictícia: registry/, RETOMADA.md, os projetos, os hooks e o kit iguais aos da skill."""
    raiz = base / "Fundacao Ensaio"
    for pasta in ("registry", f"projects/{projeto}", *(f"projects/{o}" for o in outros), ".claude/hooks"):
        (raiz / pasta).mkdir(parents=True, exist_ok=True)
    (raiz / "RETOMADA.md").write_text("# RETOMADA de ensaio\n", encoding="utf-8")
    for nome in TODOS_OS_HOOKS:
        shutil.copyfile(skill / "assets" / "hooks" / nome, raiz / ".claude" / "hooks" / nome)
    shutil.copytree(skill / "assets" / "fundacao-kit" / "fundacao", raiz / "fundacao")
    return raiz


def ficha_de_ensaio(projeto: str, versao: int = 1, **secoes) -> dict:
    return {"schema_version": "fundacao.ficha_aberturas/1", "ficha_id": f"ficha-{projeto}-v{versao}",
            "project_id": projeto, "versao": versao, "motivo": "ensaio", "consequencias": "ensaio", **secoes}


def gravar_ficha_na_caixa(raiz: Path, projeto: str, ficha: dict) -> Path:
    caixa = raiz / ".claude" / "projetos" / projeto / "ficha"
    caixa.mkdir(parents=True, exist_ok=True)
    arquivo = caixa / f"ficha-v{ficha['versao']}.json"
    arquivo.write_text(json.dumps(ficha, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    (caixa / (arquivo.name + ".sig")).write_text("assinatura de ensaio v" + str(ficha["versao"]) + "\n",
                                                 encoding="utf-8")
    return arquivo


def aceite_de_ensaio(projeto: str, relatorio_sha256: str, claude_sha256: str, forma: str, *, aceito_em: str,
                     vigencia_ate: str, confina=False, versao: int = 1) -> dict:
    """Aceite de risco do canário (1.7.10.1) no esquema da ferramenta do titular, de ensaio."""
    return {"schema_version": "fundacao.aceite_risco_canario/1", "project_id": projeto, "versao": versao,
            "aceito_em": aceito_em, "vigencia_ate": vigencia_ate, "riscos": ["risco de ensaio"],
            "canario": {"relatorio_sha256": relatorio_sha256, "claude_versao": "2.1.302",
                        "claude_sha256": claude_sha256, "forma": forma, "confina_comandos": confina,
                        "data": "2026-10-31T12:00:00Z", "falhou": ["plugin_setting_sources_local"],
                        "nao_medido": ["leitura_state"], "vazou": []}}


def gravar_aceite_na_caixa(raiz: Path, projeto: str, aceite: dict, *, assinatura: bytes | None = None) -> Path:
    """O que a ferramenta do titular grava: o aceite na forma canônica e a assinatura de ensaio (a do substituto do
    kit, `conferir_assinatura`, que cita o SHA-256 dos bytes)."""
    caixa = raiz / ".claude" / "projetos" / projeto / "risco"
    caixa.mkdir(parents=True, exist_ok=True)
    bruto = (json.dumps(aceite, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    (caixa / "aceite-risco-canario.json").write_bytes(bruto)
    (caixa / "aceite-risco-canario.json.sig").write_bytes(
        assinatura if assinatura is not None
        else ("assinatura de ensaio " + hashlib.sha256(bruto).hexdigest() + "\n").encode("ascii"))
    return caixa / "aceite-risco-canario.json"


def relatorio_de_canario(m, raiz: Path, claude: Path, *, versao: str = "2.1.302", **mudancas) -> dict:
    """Relatório `fundacao.ensaio_isolamento/1` de ensaio (o formato do pacote CANARIO), aprovado, do Claude Code de
    ensaio e da forma de caminho da raiz de ensaio, medida como o preparo mede. Pasta temporária num sistema de arquivos
    que o canário não prova (tmpfs, por exemplo): o teste é pulado, com o motivo. Completo como o do ensaio real
    (revisão de segurança da 1.7.10, CAN-1: o portão recalcula a conclusão pelos itens): as sondas de
    `m.SONDAS_DO_CANARIO`, cada uma de comando com `passou`, o perfil gerado, o sandbox ligado e o temp do lançador."""
    fs = m.tipo_de_fs(raiz)
    forma = m.forma_do_caminho(Path(raiz).as_posix(), fs)
    if forma is None:
        raise unittest.SkipTest(f"a pasta temporária fica num sistema de arquivos ({fs}) que o canário não prova")
    forma = "ext4" if forma == "ext4" else forma + "/ensaio-canario"
    itens = [{"id": ident, "classe": classe, "veredito": "nao_medido" if classe == "informativo" else "passou",
              "motivo": "ensaio"} for ident, classe in m.SONDAS_DO_CANARIO.items()]
    relatorio = {"schema_version": "fundacao.ensaio_isolamento/1", "data": "2026-10-31T12:00:00Z", "simulado": False,
                 "forma": forma, "base": "/home/ensaio/canario", "projeto": "ensaio-a",
                 "claude": {"binario": "/home/ensaio/claude", "versao": versao, "sha256": sha(claude)},
                 "sistema_de_arquivos": fs, "sandbox_ligado": True, "seccomp_presente": None,
                 "perfil": {"gerado": True, "veredito": "passou"}, "temp": {"base": "/tmp", "do_lancador": True},
                 "itens": itens,
                 "conclusao": {"forma": forma, "sistema_de_arquivos": fs, "confina_comandos": True, "motivo": "ensaio"}}
    relatorio.update(mudancas)
    return relatorio


def instalar_canario(skill: Path, base: Path, relatorio: dict, *extra) -> subprocess.CompletedProcess:
    """`instalar-canario` em modo de ensaio (área em pasta da base, sem root)."""
    arquivo = base / "relatorio-canario.json"
    arquivo.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return subprocess.run([PYTHON_LINUX if Path(PYTHON_LINUX).exists() else sys.executable, "-I", "-B",
                           str(skill / "assets" / "host" / "preparo_host.py"), "instalar-canario", "--relatorio",
                           str(arquivo), "--area-raiz", str(base / "area"), *map(str, extra)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV, timeout=120)


def claude_de_ensaio(pasta: Path) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    binario = pasta / "claude"
    binario.write_text(CLAUDE_FALSO, encoding="utf-8", newline="\n")
    binario.chmod(0o755)
    return binario


def usuario_atual() -> str:
    import getpass
    return getpass.getuser()


def instalar(skill: Path, raiz: Path, base: Path, projeto: str = "caso-real", claude: Path | None = None,
             *extra, simular: bool = False, sonda_cmd: Path | None = None) -> subprocess.CompletedProcess:
    """`instalar-projeto` em modo de ensaio: área, lançador, temp e sondas em pastas da base, sem root."""
    claude = claude or claude_de_ensaio(base / "claude-ensaio")
    args = [PYTHON_LINUX if Path(PYTHON_LINUX).exists() else sys.executable, "-I", "-B",
            str(skill / "assets" / "host" / "preparo_host.py"), "instalar-projeto", "--raiz", str(raiz), "--projeto",
            projeto, "--titular", "titular", "--claude", str(claude), "--claude-versao", "2.1.302", "--claude-sha256",
            sha(claude), "--origem-hash", "ensaio", "--perfil-windows", "/mnt/c/Users/<usuario>", "--casa",
            str(base / "home"), "--usuario", usuario_atual(), "--area-raiz", str(base / "area"), "--bin",
            str(base / "bin"), "--temp-base", str(base / "tmp"), "--sonda-interop-cmd",
            str(sonda_cmd or (base / "sem-interop" / "cmd.exe")), "--sonda-interop-binfmt",
            str(base / "sem-interop" / "binfmt"), "--gerenciadas", str(base / "claude-code-gerenciado"),
            *map(str, extra)]
    if simular:
        args.append("--simular")
    (base / "tmp").mkdir(exist_ok=True)
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV,
                          timeout=300)


class TestApoioDeEnsaio(unittest.TestCase):
    """O apoio só substitui as peças dos outros pacotes; o resto da cópia é igual à skill."""

    def test_copia_da_skill_e_substitutos(self):
        import tempfile
        base = Path(tempfile.mkdtemp(prefix="apoio-host-1710-"))
        try:
            skill = skill_de_ensaio(base)
            self.assertEqual(sha(skill / "assets" / "host" / "preparo_host.py"),
                             sha(SKILL / "assets" / "host" / "preparo_host.py"))
            for nome in ("guarda_caminho.py", "guarda_identidade.py", "sinais_sessao.py"):
                self.assertEqual(sha(skill / "assets" / "hooks" / nome), sha(SKILL / "assets" / "hooks" / nome))
            for nome in TODOS_OS_HOOKS:
                self.assertTrue((skill / "assets" / "hooks" / nome).is_file(), nome)
            self.assertIn("Porteiro de ensaio", (skill / "assets" / "host" / "wsl" / "porteiro.py").read_text(
                encoding="utf-8"))
            raiz = raiz_de_ensaio(base, skill)
            m = carregar_preparo(skill)
            self.assertEqual(m.sha256_arvore(raiz / "fundacao"),
                             m.sha256_arvore(skill / "assets" / "fundacao-kit" / "fundacao"))
            # a conta do kit vem do porteiro da skill (aqui, o substituto), importável sem rodar a linha de comando
            self.assertEqual(m.kit_sha256(raiz, skill), m.kit_sha256(skill / "assets" / "fundacao-kit", skill))
            self.assertFalse((base / "porteiro-chamadas.jsonl").exists())
        finally:
            shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
