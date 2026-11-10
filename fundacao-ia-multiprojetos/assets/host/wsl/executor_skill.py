#!/usr/bin/env python3
"""Executor das skills com scripts (1.7.11, lote S3; desenho de skills e agentes, §3.3 e §3.4).

Roda pelo lançador `/usr/local/bin/fundacao-skill-<projeto>` (dono root, gerado pelo preparo, com o SHA-256 deste
arquivo fixado), como o usuário da sessão, nunca como root:

    fundacao-skill-<p> <plugin>:<skill> <script> [-- <argumentos do script>...]

Só roda o script que a ficha aplicada lista (`aberturas.json` da área root), pelo NOME dele, nunca por caminho, e só se,
antes de CADA execução, tudo confere (falha fechada, código 2, nada roda): o projeto do hashes.json é o do lançador; a
pasta atual real fica em `projects/<p>/` e a variável FUNDACAO_PROJECT é `<p>` (obrigatória); o SHA-256 do script na
cópia root é o da ficha; o interpretador real e a árvore da venv são os que o preparo gravou no hashes.json (as mesmas
funções do `preparo_skills.py`, `arvore_da_venv` e `sha256_da_venv`). O script roda com `<python> -I -B <script>
<argumentos>`: o caminho do script vem da ficha e é absoluto, então nenhum argumento vira opção do Python. O ambiente é
mínimo (PATH fixo, HOME, TMPDIR, LANG, FUNDACAO_PROJECT e as variáveis de proxy do sandbox). Cada execução deixa duas
linhas em `projects/<p>/outputs/skills/registro.jsonl` (início e fim), e sem o registro gravado o script não roda.

Limites que ficam: no modo `sessao` o script tem a autoridade dos comandos da sessão (o executor prova a integridade do
que roda, não o que ele faz); o modo `caixa` (a operação `rodar` do porteiro) é do lote S4 e fica FECHADO aqui; a sessão
pode rodar qualquer código por fora do executor, e a trava de projeto é lógica. As opções `--area` e `--skills-base` são do
lançador (e dos testes): chamar este arquivo direto com outra área não dá poder além do que a sessão já tem. Só
biblioteca padrão.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import time
import types
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SKILL = AQUI.parent.parent.parent  # <cópia root da skill>/assets/host/wsl/executor_skill.py
AREA_RAIZ = "/etc/fundacao-ia"
SKILLS_BASE = "/usr/local/lib/fundacao-ia/skills"
TETO_JSON, TETO_ARGUMENTOS, TETO_ARGUMENTO = 1 << 20, 64, 4096
PROJETO = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")
ALVO = re.compile(r"^([a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?):([A-Za-z0-9][A-Za-z0-9._-]{0,63})$")
NOME_DO_SCRIPT = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
CAMINHO = re.compile(r"^skills/([A-Za-z0-9][A-Za-z0-9._-]{0,63})/scripts/[a-z][a-z0-9_]{0,31}\.py$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
IDIOMA = re.compile(r"^[A-Za-z0-9_.@-]{1,40}$")
PATH_FIXO = "/usr/bin:/bin"
PROXIES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy")
REFAZER = "rode de novo o preparar-wsl.sh (com sudo)"
_MODULOS: dict = {}


class Recusa(ValueError):
    """Qualquer motivo para não rodar: vira a mensagem e o código 2."""


def _carregar(nome: str, caminho: Path):
    if nome not in _MODULOS:
        if not caminho.is_file():
            raise Recusa(f"{caminho} ausente: a cópia root da skill está incompleta; {REFAZER}")
        sys.dont_write_bytecode = True
        spec = importlib.util.spec_from_file_location(f"_executor_skill_{nome}", caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        _MODULOS[nome] = modulo
    return _MODULOS[nome]


def copia_segura():
    return _carregar("copia_segura", SKILL / "scripts" / "copia_segura.py")


def preparo_skills():
    """O `preparo_skills.py` desta cópia da skill (a conta da venv é a do preparo), ligado a este executor."""
    ja = "preparo_skills" in _MODULOS
    modulo = _carregar("preparo_skills", AQUI.parent / "preparo_skills.py")
    if not ja:
        modulo.configurar(types.SimpleNamespace(EntradaInvalida=Recusa, _carregar_script=lambda n: copia_segura()))
    return modulo


def ler_json(arquivo: Path) -> dict:
    """JSON de arquivo comum, sem seguir ligação nem vínculo físico, até TETO_JSON bytes."""
    try:
        fd = copia_segura().abrir_comum(arquivo)
        try:
            dados = b""
            while len(dados) <= TETO_JSON and (bloco := os.read(fd, 1 << 16)):
                dados += bloco
        finally:
            os.close(fd)
        if len(dados) > TETO_JSON:
            raise Recusa(f"{arquivo.name} acima do teto de {TETO_JSON} bytes")
        valor = json.loads(dados.decode("utf-8-sig"))
    except (OSError, ValueError) as exc:
        if isinstance(exc, Recusa):
            raise
        raise Recusa(f"{arquivo} ausente, ilegível ou fora da forma ({str(exc)[:120]}); {REFAZER}") from None
    if not isinstance(valor, dict):
        raise Recusa(f"{arquivo.name} fora da forma (não é um objeto)")
    return valor


# ------------------------------------------------------------------ a linha de comando
def analisar(argv: list[str]) -> dict:
    """`--projeto P [--area A] [--skills-base S] -- <plugin>:<skill> <script> [-- args...]` (o lançador monta a primeira
    parte; o que a sessão digita fica depois do primeiro `--`). Qualquer outra forma: Recusa."""
    if "--" not in argv:
        raise Recusa("uso: fundacao-skill-<projeto> <plugin>:<skill> <script> [-- argumentos do script]")
    i = argv.index("--")
    opcoes, resto, valores = argv[:i], argv[i + 1:], {}
    if len(opcoes) % 2 or any(o not in ("--projeto", "--area", "--skills-base") or opcoes.count(o) != 1
                              for o in opcoes[::2]):
        raise Recusa("o lançador passou opções fora da forma")
    valores = {o[2:].replace("-", "_"): v for o, v in zip(opcoes[::2], opcoes[1::2])}
    if not PROJETO.match(valores.get("projeto", "")) or "--" in valores["projeto"]:
        raise Recusa("projeto do lançador fora da forma")
    for chave in ("area", "skills_base"):
        if not os.path.isabs(valores.get(chave, "/")):
            raise Recusa(f"{chave.replace('_', '-')} do lançador precisa ser caminho absoluto")
    if len(resto) < 2:
        raise Recusa("uso: fundacao-skill-<projeto> <plugin>:<skill> <script> [-- argumentos do script]")
    alvo, script, extras = resto[0], resto[1], resto[2:]
    m = ALVO.match(alvo)
    if not m or not NOME_DO_SCRIPT.match(script):
        raise Recusa(f"{alvo!r} {script!r}: use o NOME do plugin e da skill (<plugin>:<skill>) e o NOME do script da "
                     "ficha, nunca um caminho")
    if extras and extras[0] != "--":
        raise Recusa("os argumentos do script vão depois de um `--`: fundacao-skill-<p> <plugin>:<skill> <script> -- ...")
    args = extras[1:]
    if len(args) > TETO_ARGUMENTOS or any(len(a) > TETO_ARGUMENTO for a in args):
        raise Recusa(f"no máximo {TETO_ARGUMENTOS} argumentos de até {TETO_ARGUMENTO} caracteres")
    return {**valores, "area": Path(valores.get("area", f"{AREA_RAIZ}/projetos/{valores['projeto']}")),
            "skills_base": Path(valores.get("skills_base", SKILLS_BASE)), "plugin": m.group(1), "skill": m.group(2),
            "alvo": alvo, "script": script, "args": args}


# ------------------------------------------------------------------ as conferências (antes de cada execução)
def achar(ficha: dict, pedido: dict) -> tuple[dict, dict]:
    """(skill, script) que a ficha aplicada lista para o pedido; fora dela, Recusa."""
    if ficha.get("projeto") != pedido["projeto"] or ficha.get("valida") is not True:
        raise Recusa("a ficha aplicada deste projeto não vale (ou é de outro projeto); nada roda")
    plugins = ficha.get("plugins")
    for p in plugins if isinstance(plugins, list) else []:
        if not isinstance(p, dict) or p.get("nome") != pedido["plugin"]:
            continue
        for s in p.get("skills_com_scripts") or []:
            if not isinstance(s, dict) or s.get("skill") != pedido["skill"]:
                continue
            for sc in s.get("scripts") or []:
                if isinstance(sc, dict) and sc.get("nome") == pedido["script"]:
                    return s, sc
    raise Recusa(f"o script {pedido['script']!r} da skill {pedido['alvo']} não está na ficha aplicada deste projeto")


def conferir_pasta_e_projeto(hashes: dict, pedido: dict, cwd: str, ambiente) -> Path:
    """A pasta atual real fica em `projects/<p>/` e a variável do projeto é `<p>`, obrigatória (trava lógica: a sessão de
    outro projeto alcança este executor). Devolve a pasta do projeto."""
    raiz, projeto = hashes.get("raiz"), pedido["projeto"]
    if hashes.get("projeto") != projeto or not isinstance(raiz, str) or not os.path.isabs(raiz):
        raise Recusa("o hashes.json da área é de outro projeto ou está fora da forma; " + REFAZER)
    proj, copia = Path(raiz) / "projects" / projeto, copia_segura()
    for pasta in (proj.parent, proj):
        try:
            st = os.lstat(pasta)
        except OSError:
            raise Recusa(f"{pasta.as_posix()} ausente") from None
        if copia.e_ligacao(st) or not stat.S_ISDIR(st.st_mode):
            raise Recusa(f"{pasta.as_posix()} é ligação ou não é pasta")
    atual, base = Path(os.path.realpath(cwd)), Path(os.path.realpath(proj))
    if atual != base and base not in atual.parents:
        raise Recusa(f"este executor é do projeto {projeto}: a pasta atual ({atual.as_posix()}) não fica em "
                     f"{base.as_posix()}. Rode a partir da sessão do projeto {projeto}")
    if ambiente.get("FUNDACAO_PROJECT") != projeto:  # obrigatória: `env -u FUNDACAO_PROJECT` não abre a trava
        raise Recusa(f"este executor é do projeto {projeto}: a variável FUNDACAO_PROJECT da sessão tem de ser {projeto} "
                     f"(está {'ausente' if 'FUNDACAO_PROJECT' not in ambiente else 'em outro valor'}). Rode a partir da "
                     f"sessão do projeto {projeto}")
    return proj


def conferir_script(pedido: dict, skill: dict, sc: dict) -> Path:
    """O script na cópia root, sem seguir ligação, com o SHA-256 da ficha; o caminho é o da ficha, na forma fixa."""
    m = CAMINHO.match(str(sc.get("caminho")))
    if not m or m.group(1) != pedido["skill"] or not SHA256.match(str(sc.get("sha256"))):
        raise Recusa(f"o script {pedido['script']} da ficha tem caminho ou hash fora da forma")
    pasta = pedido["area"] / "plugins" / pedido["plugin"]
    arquivo = pasta.joinpath(*sc["caminho"].split("/"))
    try:
        atual = copia_segura().hash_conferido(arquivo, dentro_de=pasta)["sha256"]
    except OSError as exc:
        raise Recusa(f"o script {sc['caminho']} não foi lido sem ligação na cópia root ({str(exc)[:120]}); {REFAZER}") from None
    if atual != sc["sha256"]:
        raise Recusa(f"o script {sc['caminho']} mudou desde a assinatura (esperado {sc['sha256'][:12]}..., encontrado "
                     f"{atual[:12]}...): não roda. Se a mudança foi sua, assine a ficha de novo e {REFAZER}")
    return arquivo


def conferir_interpretador_e_venv(hashes: dict, pedido: dict, skill: dict) -> str:
    """O interpretador e a venv reconferidos contra o hashes.json (as funções do preparo). Devolve o python que roda:
    o da venv, ou o do sistema (só biblioteca padrão) quando a skill não tem pacotes."""
    ps, registro = preparo_skills(), hashes.get("skills")
    registro = registro.get(pedido["alvo"]) if isinstance(registro, dict) else None
    if not isinstance(registro, dict):
        raise Recusa(f"o hashes.json não registra o interpretador da skill {pedido['alvo']}; {REFAZER}")
    dep, venv = skill.get("dependencias"), registro.get("venv")
    esperada = None
    if dep:
        lock = dep.get("lock_sha256") if isinstance(dep, dict) else None
        if not isinstance(venv, dict) or not SHA256.match(str(lock)) or venv.get("lock_sha256") != lock:
            raise Recusa(f"a venv registrada de {pedido['alvo']} não é a do lock da ficha; {REFAZER}")
        esperada = pedido["skills_base"] / pedido["projeto"] / pedido["plugin"] / lock[:12] / "venv"
    elif venv is not None:
        raise Recusa(f"a ficha de {pedido['alvo']} não tem pacotes, e o hashes.json registra uma venv; {REFAZER}")
    problemas = ps.problemas_da_skill(pedido["alvo"], registro, esperada)
    if problemas:
        raise Recusa("; ".join(problemas[:3]))
    return (Path(venv["caminho"]) / "bin" / "python").as_posix() if venv else registro["interpretador"]["caminho"]


# ------------------------------------------------------------------ o que roda
def ambiente_do_script(origem, projeto: str) -> dict:
    """O ambiente mínimo: PATH fixo, HOME e TMPDIR absolutos (ou o padrão), LANG simples, o projeto e as variáveis de
    proxy do sandbox (nomes fixos). Mais nada da sessão passa (PYTHON*, LD_*, segredos)."""
    def texto(nome, vale):
        v = origem.get(nome)
        return v if isinstance(v, str) and vale(v) and not any(c in v for c in "\0\n\r") else None
    env = {"PATH": PATH_FIXO, "FUNDACAO_PROJECT": projeto, "LANG": texto("LANG", IDIOMA.match) or "C.UTF-8",
           "HOME": texto("HOME", os.path.isabs) or "/nonexistent", "TMPDIR": texto("TMPDIR", os.path.isabs) or "/tmp"}
    for nome in PROXIES:
        if (v := texto(nome, lambda s: len(s) <= 1024)) is not None:
            env[nome] = v
    return env


def rodar(argv: list[str], env: dict, cwd: str) -> int:
    """Roda o programa com a entrada e as saídas da sessão. Os testes de unidade trocam esta função."""
    try:
        return subprocess.run(argv, env=env, cwd=cwd, close_fds=True).returncode
    except OSError as exc:
        raise Recusa(f"o interpretador não abriu ({exc.strerror or exc})") from None


def registrar(proj: Path, linha: dict) -> None:
    """Uma linha em `outputs/skills/registro.jsonl` do projeto: nenhum nível é ligação, o arquivo é comum e só cresce."""
    pasta, copia = proj, copia_segura()
    for parte in ("outputs", "skills"):
        pasta = pasta / parte
        try:
            st = os.lstat(pasta)
        except FileNotFoundError:
            os.mkdir(pasta, 0o755)
            st = os.lstat(pasta)
        if copia.e_ligacao(st) or not stat.S_ISDIR(st.st_mode):
            raise OSError(f"{pasta.as_posix()} é ligação ou não é pasta")
    marcas = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(pasta / "registro.jsonl", marcas, 0o644)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            raise OSError("registro.jsonl não é arquivo comum de um nome só")
        os.write(fd, (json.dumps(linha, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    finally:
        os.close(fd)


def executar(argv: list[str], ambiente=None, cwd: str | None = None) -> int:
    """O executor inteiro. Devolve o código do script, ou 2 se algo não conferiu (nada rodou)."""
    ambiente = os.environ if ambiente is None else ambiente
    inicio = time.monotonic()
    proj = pedido = None
    try:
        pedido = analisar(argv)
        ficha = ler_json(pedido["area"] / "aberturas.json")
        hashes = ler_json(pedido["area"] / "hashes.json")
        skill, sc = achar(ficha, pedido)
        if sc.get("modo") != "sessao":
            raise Recusa(f"o modo {sc.get('modo')!r} do script {pedido['script']} está fechado: o modo caixa (a operação "
                         "`rodar` do porteiro) é do lote S4 e não existe nesta versão; só o modo sessao roda")
        try:
            cwd = cwd or os.getcwd()
        except OSError:
            raise Recusa("a pasta atual não existe mais: entre na pasta do projeto e rode de novo") from None
        proj = conferir_pasta_e_projeto(hashes, pedido, cwd, ambiente)
        arquivo = conferir_script(pedido, skill, sc)
        python = conferir_interpretador_e_venv(hashes, pedido, skill)
        resumo = [a[:120] + ("..." if len(a) > 120 else "") for a in pedido["args"][:16]]
        base = {"plugin": pedido["plugin"], "skill": pedido["skill"], "script": pedido["script"], "sha256": sc["sha256"],
                "argc": len(pedido["args"]), "argv": resumo}
        try:  # sem a trilha, o script não roda
            registrar(proj, {**base, "fase": "inicio", "hora": _agora(),
                             "conferencia_s": round(time.monotonic() - inicio, 2)})
        except OSError as exc:
            raise Recusa(f"o registro em outputs/skills não foi gravado ({str(exc)[:150]})") from None
        argv_final = [python, "-I", "-B", arquivo.as_posix(), *pedido["args"]]
        env = ambiente_do_script(ambiente, pedido["projeto"])
    except Recusa as exc:
        print(f"fundacao-skill{'-' + pedido['projeto'] if pedido else ''}: recusado, nada rodou: {exc}", file=sys.stderr)
        return 2
    t0 = time.monotonic()
    try:
        codigo = rodar(argv_final, env, cwd)
    except Recusa as exc:
        print(f"fundacao-skill-{pedido['projeto']}: {exc}", file=sys.stderr)
        codigo = 2
    codigo = 128 - codigo if codigo < 0 else codigo  # morto por sinal: 128 + número, como o shell
    try:
        registrar(proj, {**base, "fase": "fim", "hora": _agora(), "codigo": codigo, "duracao_s": round(time.monotonic() - t0, 2)})
    except OSError as exc:
        print(f"aviso: o fim da execução não foi registrado ({str(exc)[:150]})", file=sys.stderr)
    return codigo


def _agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    sys.exit(executar(sys.argv[1:]))
