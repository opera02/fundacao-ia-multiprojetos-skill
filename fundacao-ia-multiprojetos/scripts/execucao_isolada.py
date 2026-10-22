#!/usr/bin/env python3
"""Lançador único do código importado no Fluxo B (B6–B8): plano explícito, preso por SHA-256, e contenção.

O `caracterizar.py` roda cada caso por aqui [Decisão; auditoria Codex Security da 1.7.6, #1: a "cópia isolada" do
B6 só trocava a pasta de trabalho]. O plano diz tudo o que o programa recebe — isolamento, programa (caminho e
SHA-256) e comando, cópia e SHA-256 do manifesto dela, pasta de trabalho, entradas, pasta gravável, ambiente, rede e
limites —, e o titular aprova o SHA-256 do JSON canônico. O hash prende o programa (`comando[0]`, quase sempre o
interpretador), não o script que ele roda: esse fica preso pelo manifesto da cópia, obrigatório com `--copia`; o comando
não cita arquivo fora da cópia, e o plano lista o que a cópia tem e o manifesto não vê. Sem cópia (só sem isolamento),
o plano marca o código como não preso [revisão de segurança da 1.7.7, R177-FB-02]; com ela, também, e com os motivos,
se a pasta de trabalho, uma variável pedida ou `{entrada}`/`{ensaio}` no lugar do script trazem código de fora do que
o manifesto prende [segunda passada, R177B-B-02]. Programa, manifesto e cópia são conferidos na montagem e antes e
depois de cada caso: divergência para a execução [R177B-B-03]. O que prende o código fica em `codigo_do_plano.py`; o
texto da folha de decisões sai de `folha_do_plano.py`.
- `bwrap` (Linux/WSL, com um bubblewrap que abre de fato): `--unshare-all` (rede só com o `lo` próprio, PIDs
  próprios), `--die-with-parent`, `--new-session`, `--clearenv`; `/usr`, as ligações `/bin`, `/lib`... e `/etc` só
  leitura; `/proc`, `/dev` e `/tmp` próprios (HOME e TMPDIR em `/tmp`); cópia e entrada do caso só leitura; gravável
  só a pasta do caso. Entradas e `--pasta-saida` ficam na cópia ou no projeto da fundação que a contém, e a pasta
  gravável não contém a cópia [R177-FB-01]; fora isso, nada da pasta pessoal, da raiz da fundação, de `state/` ou de
  outros projetos, nem ligação.
- `nenhum`: só com motivo (`--sem-isolamento`), que vai para o plano: o programa tem toda a autoridade da conta.
Nos dois: ambiente mínimo mais as variáveis pedidas uma a uma (segredo nunca; `FUNDACAO_*` só pelo nome), entrada
padrão vazia, saída com teto, limites do SO e a árvore de processos encerrada no prazo, no teto, no fim normal e se o
lançador morrer (Windows: Job Object com o processo criado suspenso; Linux: grupo de processos, varredura dos órfãos,
que o lançador adota como subreaper, e sinal de morte do pai; no bubblewrap, o espaço de PIDs morre junto). Limites:
mesmo kernel e mesma conta (falha do kernel ou do bwrap escapa); `/usr` e `/etc` legíveis; fora do Linux e do
Windows, só o grupo de processos.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
ESQUEMA = "fundacao.plano-execucao/3"  # 3: por que o código não fica preso e a pasta gravável na cópia [R177B-B-02/03]
PATH_ISOLADO = "/usr/local/bin:/usr/bin:/bin"
CASA = "<pasta temporária do caso>"  # sem isolamento: HOME e TMP apontam para ela, criada e apagada a cada caso
REDE_NEGADA = "negada: o sandbox só tem o lo próprio (--unshare-net)"
REDE_DA_CONTA = "a da conta, sem bloqueio"
CODIGO_PRESO = ("preso pelo manifesto da cópia, conferido na montagem e antes e depois de cada caso (menos o que está "
                "em manifesto.fora_do_manifesto e na pasta gravável que fica na cópia)")
CODIGO_SOLTO = ("NÃO PRESO: o SHA-256 prende só o programa; o script e os módulos que ele roda podem mudar sem mudar o "
                "plano (sem --copia e --manifesto)")
SEM_COPIA = "sem --copia e --manifesto, o SHA-256 prende só o programa"
NOMES_DE_SEGREDO = ("KEY", "TOKEN", "SECRET", "PASSW", "CREDENTIAL", "SENHA", "CHAVE")
_SISTEMA_WINDOWS = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT")
_FIXOS = ["--unshare-all", "--die-with-parent", "--new-session", "--clearenv"]
_MIB = 1024 * 1024
SEM_ISOLAMENTO_AQUI = (
    "recusado: não há isolamento aqui ({motivo}). O código importado rodaria com toda a autoridade da sua conta: lê e "
    "grava o que você lê e grava, e usa a rede. Caminho certo: rode o B6 no WSL (Ubuntu), onde o preparo do host "
    "(assets/host/wsl/preparar-wsl.sh) instala o bubblewrap; se a sessão do WSL não abrir o sandbox, o titular roda "
    "o mesmo comando no terminal do Ubuntu. Só para fixture própria e fictícia: --sem-isolamento \"<motivo>\"")


def _carregar(nome: str):
    """Um script ao lado deste, pelo caminho (sem mexer no `sys.path`)."""
    spec = importlib.util.spec_from_file_location(f"_execucao_isolada_{nome}", AQUI / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


CODIGO = _carregar("codigo_do_plano")  # o que prende o código que o programa roda (manifesto da cópia)
Recusa = CODIGO.Recusa  # a mesma classe nos dois: quem chama sai com código 2 e a mensagem
_dentro = CODIGO.dentro  # comparação do texto do caminho, sem resolver ligação


def limites(timeout: int, teto_mb: int = 32, memoria_mb: int = 4096, arquivo_mb: int = 512, processos: int = 256) -> dict:
    valores = {"tempo_s": timeout, "cpu_s": timeout, "saida_bytes": teto_mb * _MIB, "memoria_bytes": memoria_mb * _MIB,
               "arquivo_bytes": arquivo_mb * _MIB, "processos": processos}
    if any(not isinstance(v, int) or v <= 0 for v in valores.values()):
        raise Recusa("os limites do plano são inteiros positivos (tempo, saída, memória, arquivo, processos)")
    return {**valores, "aplicados_pelo_so": "Job Object: memória, CPU e processos (tamanho de arquivo não existe no "
            "Windows)" if os.name == "nt" else "setrlimit: AS, CPU, FSIZE e, no Linux, NPROC além dos da conta"}


def montagens_do_sistema() -> list[list[str]]:
    montagens = [["ro-bind", "/usr", "/usr"]]
    for pasta in ("/bin", "/sbin", "/lib", "/lib64", "/lib32", "/libx32"):
        if os.path.islink(pasta):
            montagens.append(["symlink", os.readlink(pasta), pasta])
        elif os.path.isdir(pasta):
            montagens.append(["ro-bind", pasta, pasta])
    return montagens + [["ro-bind", "/etc", "/etc"], ["proc", "/proc"], ["dev", "/dev"], ["tmpfs", "/tmp"]]


def _argv_montagens(montagens: list[list[str]]) -> list[str]:
    return [item for tipo, *caminhos in montagens for item in (f"--{tipo}", *caminhos)]


def sondar_bwrap() -> tuple[str | None, str]:
    """(caminho do bwrap, "") se ele abre aqui um sandbox com as montagens do plano; (None, motivo) se não."""
    if not sys.platform.startswith("linux"):
        return None, f"sistema {sys.platform}: o bubblewrap só existe no Linux/WSL"
    caminho = shutil.which("bwrap")
    if not caminho:
        return None, "bubblewrap (bwrap) não encontrado no PATH"
    try:
        r = subprocess.run([caminho, *_FIXOS, *_argv_montagens(montagens_do_sistema()), "--", "/bin/true"],
                           capture_output=True, env={}, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"o bwrap não abriu ({type(exc).__name__})"
    if r.returncode != 0:
        return None, "o bwrap não abriu o sandbox: " + r.stderr.decode("utf-8", "replace").strip()[-300:]
    return caminho, ""


def _variaveis(pedidas: list[str]) -> dict:
    """`NOME` (valor do ambiente de quem chama) ou `NOME=VALOR`; segredo nunca, `FUNDACAO_*` só pelo nome."""
    extras = {}
    for item in pedidas:
        nome, igual, valor = item.partition("=")
        if not nome or not nome.replace("_", "").isalnum():
            raise Recusa(f"--variavel {item!r}: nome inválido")
        if any(s in nome.upper() for s in NOMES_DE_SEGREDO):
            raise Recusa(f"--variavel {nome}: nome de segredo não passa ao código executado (importar segredo é uma "
                         "decisão à parte, na folha de decisões)")
        if igual and nome.upper().startswith("FUNDACAO_"):
            raise Recusa(f"--variavel {nome}=...: FUNDACAO_* vai só pelo nome; o valor vem do lançador, nunca do comando")
        if not igual and nome not in os.environ:
            raise Recusa(f"--variavel {nome}: ausente no ambiente de quem chama")
        extras[nome] = valor if igual else os.environ[nome]
    return extras


def _sha256_de(caminho: str) -> str:
    h = hashlib.sha256()
    try:
        with open(caminho, "rb") as f:
            for bloco in iter(lambda: f.read(1 << 20), b""):
                h.update(bloco)
    except OSError as exc:
        raise Recusa(f"programa {caminho} ilegível ({type(exc).__name__})") from None
    return h.hexdigest()


def _programa(nome: str, path: str, cwd: str) -> dict:
    """O programa, resolvido pelo PATH do plano (ou pela pasta de trabalho, se vier com pasta), e o SHA-256 dele."""
    caminho = os.path.join(cwd, nome) if os.path.dirname(nome) else shutil.which(nome, path=path)
    if not caminho or not os.path.isfile(caminho):
        raise Recusa(f"programa {nome!r} não encontrado (PATH do plano ou pasta de trabalho)")
    return {"caminho": os.path.abspath(caminho), "sha256": _sha256_de(caminho)}


def projeto_da_copia(copia: str | None) -> str | None:
    """A pasta do projeto da fundação que contém a cópia (`<raiz>/projects/<projeto>`, com `<raiz>/state/state.sqlite`);
    fora de uma fundação, None."""
    for pasta in ((Path(copia), *Path(copia).parents) if copia else ()):
        if pasta.parent.name == "projects" and (pasta.parent.parent / "state" / "state.sqlite").exists():
            return str(pasta)
    return None


def montar_plano(acao: str, comando: list[str], *, copia, manifesto, cwd, entradas: list[str], gravavel,
                 limites: dict, variaveis: list[str], sem_isolamento: str | None, bwrap: str | None = None) -> dict:
    """Só lê. `gravavel`: ("ensaio" | "pasta-saida", pasta) ou None; `bwrap`: caminho já sondado (None: sonda)."""
    if not comando:
        raise Recusa("plano sem comando")
    if any(marca in str(comando[0]) for marca in CODIGO.MARCAS):
        raise Recusa(f"o programa {comando[0]} não pode ser {{entrada}} nem {{ensaio}}: o plano o prende pelo SHA-256, "
                     "e ele mudaria a cada caso; ponha o programa na cópia e a entrada como argumento dele")
    extras = _variaveis(variaveis)
    if sem_isolamento is not None and not sem_isolamento.strip():
        raise Recusa("--sem-isolamento exige o motivo, em palavras: ele vai para o plano e para a folha de decisões")
    if sem_isolamento is None and bwrap is None:
        bwrap, motivo = sondar_bwrap()
        if not bwrap:
            raise Recusa(SEM_ISOLAMENTO_AQUI.format(motivo=motivo))
    isolado = sem_isolamento is None
    copia = os.path.abspath(copia) if copia else None
    if manifesto and not copia:
        raise Recusa("--manifesto exige --copia (a pasta que ele descreve)")
    if copia and not manifesto:  # revisão de segurança da 1.7.7, R177-FB-02: sem ele, o script trocado rodava
        raise Recusa(f"--copia exige --manifesto (`scripts/manifesto.py criar --raiz <cópia> --saida <manifesto>`, "
                     f"fora da cópia): o SHA-256 do plano prende só o programa ({comando[0]}); quem prende o código que "
                     "ele roda da cópia, inclusive os módulos que importa, é o manifesto, conferido a cada caso")
    cwd = os.path.abspath(cwd) if cwd else (copia or os.getcwd())
    if copia:  # o script que o comando cita fica na cópia
        CODIGO.conferir_citados(comando, cwd, copia)
    grav = {"tipo": gravavel[0], "caminho": os.path.abspath(gravavel[1])} if gravavel else None
    casa = "/tmp" if isolado else CASA
    amb = {"PATH": PATH_ISOLADO if isolado else os.environ.get("PATH", os.defpath), "HOME": casa, "TMPDIR": casa,
           "TMP": casa, "TEMP": casa}
    if os.name == "nt" and not isolado:
        amb.update({k: os.environ[k] for k in _SISTEMA_WINDOWS if k in os.environ})
        amb.update(USERPROFILE=CASA, APPDATA=CASA, LOCALAPPDATA=CASA)
    amb.update({k: v for k, v in os.environ.items() if k in ("LANG", "TZ") or k.startswith("LC_")})
    amb.update(extras)
    plano = {"schema_version": ESQUEMA, "acao": acao, "sistema": sys.platform,
             "isolamento": "bwrap" if isolado else "nenhum",
             "motivo_sem_isolamento": None if isolado else sem_isolamento.strip(),
             "comando": [str(c) for c in comando], "programa": _programa(str(comando[0]), amb["PATH"], cwd),
             "codigo_executado": CODIGO_SOLTO, "codigo_nao_preso": [SEM_COPIA], "copia": copia,
             "projeto_da_copia": projeto_da_copia(copia), "manifesto": None, "cwd": cwd,
             "entradas": sorted(os.path.abspath(e) for e in entradas),
             "gravavel": grav, "ambiente": dict(sorted(amb.items())), "variaveis_pedidas": sorted(extras),
             "rede": REDE_NEGADA if isolado else REDE_DA_CONTA, "limites": limites,
             "bwrap": bwrap if isolado else None, "montagens": [], "montagens_por_caso": []}
    if manifesto:
        try:
            dados = Path(manifesto).read_bytes()
        except OSError as exc:
            raise Recusa(f"manifesto ilegível: {manifesto} ({type(exc).__name__})") from None
        arquivo = os.path.abspath(manifesto)
        ref, politica, antigos = CODIGO.ler_manifesto(dados)  # a regra do `manifesto.py verificar` [R177B-B-01]
        na_copia = CODIGO.gravavel_na_copia(copia, grav["caminho"] if grav else None)  # fora da conferência [B-03]
        fora = CODIGO.fora_do_manifesto(copia, politica, antigos, arquivo, na_copia)
        CODIGO.conferir_presos(comando, cwd, copia, ref, fora, na_copia)  # e o manifesto o prende
        plano["manifesto"] = {"arquivo": arquivo, "sha256": hashlib.sha256(dados).hexdigest(),
                              "fora_do_manifesto": fora, "pasta_gravavel_na_copia": na_copia}
        # Preso só se nada mais muda o código: pasta de trabalho, variáveis e {entrada}/{ensaio} [R177B-B-02].
        motivos = CODIGO.motivos_nao_preso(comando, cwd, copia, plano["programa"]["caminho"], fora, extras, na_copia)
        plano["codigo_nao_preso"] = motivos
        plano["codigo_executado"] = "NÃO PRESO: " + "; ".join(motivos) if motivos else CODIGO_PRESO
    if not isolado:
        return plano
    if not copia:
        raise Recusa("no isolamento informe --copia: é a única pasta de código que o programa vê")
    if not any(_dentro(cwd, p) for p in [copia] + ([grav["caminho"]] if grav and grav["tipo"] == "pasta-saida" else [])):
        raise Recusa("no isolamento a pasta de trabalho (--cwd) fica dentro da cópia ou da --pasta-saida")
    plano["montagens"] = montagens_do_sistema() + [["ro-bind", copia, copia]]
    real = os.path.realpath(plano["programa"]["caminho"])
    if not any(_dentro(real, os.path.realpath(m[1])) for m in plano["montagens"] if m[0] == "ro-bind"):
        raise Recusa(f"o programa {plano['programa']['caminho']} fica fora do que o sandbox vê (sistema só leitura e a "
                     "cópia): use um programa do sistema (/usr) ou da cópia")
    plano["montagens_por_caso"] = ["ro-bind: a entrada do caso, no mesmo caminho absoluto", "bind (gravável): " + (
        "a pasta nova do caso, <ensaio>/caso-NNN" if grav and grav["tipo"] == "ensaio"
        else grav["caminho"] if grav else "nenhuma (só o /tmp próprio)")]
    return plano


def sha256_do_plano(plano: dict) -> str:
    texto = json.dumps(plano, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _montavel(caminho: str) -> None:
    """No isolamento: o que é montado não passa por ligação, não contém a pasta pessoal nem é raiz de fundação."""
    if os.path.realpath(caminho) != caminho:
        raise Recusa(f"{caminho} passa por ligação (link simbólico): no isolamento nada é montado através de "
                     "ligação; use o caminho real")
    if _dentro(os.path.realpath(os.path.expanduser("~")), caminho):
        raise Recusa(f"{caminho} contém a sua pasta pessoal: não pode ser montado no sandbox")
    if any(os.path.exists(os.path.join(p, "state", "state.sqlite")) for p in (caminho, os.path.dirname(caminho))):
        raise Recusa(f"{caminho} é a raiz de uma fundação ou fica direto nela (ex.: projects/ inteira): monte só a "
                     "cópia do código")


def _no_projeto(plano: dict) -> None:
    """No isolamento, entradas e `--pasta-saida` ficam na cópia ou no projeto da fundação que a contém: arquivo da pasta
    pessoal, de outro projeto ou do perfil do Windows (`/mnt/c/...`) não entra no sandbox. A pasta de ensaio fica fora
    da regra (é nova, e cada caso vê só a subpasta vazia dele); nenhuma pasta gravável contém a cópia, que deixaria de
    ser só leitura [revisão de segurança da 1.7.7, R177-FB-01]."""
    area = [p for p in (plano["copia"], plano["projeto_da_copia"]) if p]
    grav = plano["gravavel"]
    for caminho in plano["entradas"] + ([grav["caminho"]] if grav and grav["tipo"] == "pasta-saida" else []):
        if not any(_dentro(caminho, pasta) for pasta in area):
            raise Recusa(f"{caminho} fica fora da cópia e do projeto dela: no isolamento, entradas e --pasta-saida "
                         "ficam dentro da cópia ou do projeto da fundação que a contém (projects/<projeto>/); copie a "
                         "entrada para lá")
    if grav and _dentro(plano["copia"], grav["caminho"]):
        raise Recusa(f"a pasta gravável {grav['caminho']} contém a cópia, que deixaria de ser só leitura: use uma "
                     "pasta ao lado da cópia")


def conferir(plano: dict) -> None:
    """Na montagem e antes e depois de cada caso [R177B-B-03]: o programa ainda tem o SHA-256 do plano, e a cópia, o
    manifesto e o que ela tem fora dele também (`codigo_do_plano.conferir_copia`); no isolamento, o que é montado
    também, e o que o programa lê ou grava além da cópia fica nela ou no projeto dela."""
    if _sha256_de(plano["programa"]["caminho"]) != plano["programa"]["sha256"]:
        raise Recusa(f"o programa {plano['programa']['caminho']} não tem mais o SHA-256 do plano: foi trocado")
    if plano["manifesto"]:
        CODIGO.conferir_copia(plano)
    if plano["isolamento"] == "bwrap":
        for caminho in [plano["copia"], plano["cwd"], *plano["entradas"],
                        *([plano["gravavel"]["caminho"]] if plano["gravavel"] else [])]:
            _montavel(caminho)
        _no_projeto(plano)
        for entrada in plano["entradas"]:
            if not os.path.isfile(entrada):
                raise Recusa(f"entrada {entrada} não é um arquivo comum")


def argv_bwrap(plano: dict, argv: list[str], *, entrada: str | None, gravavel: str | None) -> list[str]:
    args = [plano["bwrap"], *_FIXOS]
    for nome, valor in plano["ambiente"].items():
        args += ["--setenv", nome, valor]
    args += _argv_montagens(plano["montagens"])
    args += ["--ro-bind", entrada, entrada] if entrada else []
    args += ["--bind", gravavel, gravavel] if gravavel else []
    return [*args, "--chdir", plano["cwd"], "--", *argv]


def executar(plano: dict, argv: list[str], *, entrada: str | None = None, gravavel: str | None = None) -> dict:
    """Um caso: {"codigo": int | "timeout" | "saida_acima_do_teto", "stdout": bytes, "stderr": bytes}. `argv` já vem
    com {entrada}/{ensaio} trocados; roda o programa resolvido no plano. Antes e depois, `conferir`: programa, manifesto
    ou cópia diferentes do plano param a execução, e quem chama não grava nada [R177B-B-03]."""
    _conferir_no_caso(plano, "antes do caso, que não rodou")
    argv = [plano["programa"]["caminho"], *argv[1:]]
    if plano["isolamento"] == "bwrap":
        for caminho in (entrada, gravavel):
            if caminho:
                _montavel(caminho)
        resultado = _rodar(argv_bwrap(plano, argv, entrada=entrada, gravavel=gravavel), None, {}, plano["limites"])
    else:
        casa = tempfile.mkdtemp(prefix="caracterizar-caso-")
        try:
            resultado = _rodar(argv, plano["cwd"], {k: casa if v == CASA else v for k, v in plano["ambiente"].items()},
                               plano["limites"])
        finally:
            shutil.rmtree(casa, ignore_errors=True)
    _conferir_no_caso(plano, "depois do caso: mudou enquanto ele rodava")
    return resultado


def _conferir_no_caso(plano: dict, quando: str) -> None:
    try:
        conferir(plano)
    except Recusa as exc:
        raise Recusa(f"{exc} ({quando})") from None


def _ler(fluxo, teto: int, partes: list, estourou: threading.Event) -> None:
    """Lê até o teto e descarta o resto até o fim (quem roda o caso encerra a árvore ao ver `estourou`)."""
    total = 0
    try:
        while bloco := fluxo.read1(1 << 16):
            if total < teto:
                partes.append(bloco[:teto - total])
            total += len(bloco)
            if total > teto:
                estourou.set()
    except (OSError, ValueError):
        pass


def _rodar(args: list[str], cwd: str | None, env: dict, lim: dict) -> dict:
    extra = ({"creationflags": 0x4} if os.name == "nt"  # CREATE_SUSPENDED: o Job Object vem antes da 1ª instrução
             else {"start_new_session": True, "preexec_fn": _limites_posix(lim)})
    antes = set()
    if sys.platform.startswith("linux"):
        _virar_subreaper()
        antes = {p for p, (pai, *_r) in _processos().items() if pai == os.getpid()}
    proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd,
                            env=env, **extra)
    trabalho, partes, estourou = None, {"out": [], "err": []}, threading.Event()
    try:
        if os.name == "nt":
            trabalho = _trabalho_windows(proc, lim)
        leitores = [threading.Thread(target=_ler, args=(f, lim["saida_bytes"], partes[n], estourou), daemon=True)
                    for n, f in (("out", proc.stdout), ("err", proc.stderr))]
        for t in leitores:
            t.start()
        prazo, codigo = time.monotonic() + lim["tempo_s"], None
        while codigo is None:
            if estourou.is_set() or time.monotonic() >= prazo:
                codigo = "saida_acima_do_teto" if estourou.is_set() else "timeout"
                break
            try:
                codigo = proc.wait(timeout=min(0.05, max(0.0, prazo - time.monotonic())))
            except subprocess.TimeoutExpired:
                pass
    finally:
        _encerrar(proc, trabalho, antes)  # no prazo, no teto e no fim normal: nada do caso fica rodando
    for t in leitores:
        t.join(timeout=10)
    if any(t.is_alive() for t in leitores):
        raise Recusa("a árvore de processos do caso não terminou (a saída continua aberta); pare e investigue")
    proc.stdout.close()
    proc.stderr.close()
    return {"codigo": "saida_acima_do_teto" if estourou.is_set() else codigo,
            "stdout": b"".join(partes["out"]), "stderr": b"".join(partes["err"])}


def _encerrar(proc: subprocess.Popen, trabalho, antes: set[int]) -> None:
    if trabalho is not None:
        trabalho[0].TerminateJobObject(trabalho[1], 1)
        trabalho[0].CloseHandle(trabalho[1])
    elif os.name != "nt":
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        proc.kill()
        proc.wait(timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        pass
    if sys.platform.startswith("linux"):
        _varrer(proc.pid, antes)


# --- POSIX: limites por setrlimit; Linux: subreaper e varredura dos órfãos do caso ---------------------------------
def _limites_posix(lim: dict):
    import resource
    libc, nproc, pai = None, None, os.getpid()
    if sys.platform.startswith("linux"):  # o RLIMIT_NPROC conta processos e threads da conta inteira
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
        nproc = lim["processos"] + sum(n for _p, _g, uid, n in _processos().values() if uid == os.getuid())
    pares = [("RLIMIT_AS", lim["memoria_bytes"]), ("RLIMIT_CPU", lim["cpu_s"]), ("RLIMIT_FSIZE", lim["arquivo_bytes"]),
             ("RLIMIT_NPROC", nproc)]

    def aplicar() -> None:  # no filho, entre o fork e o exec; os leitores do caso anterior já terminaram
        if libc is not None:  # PR_SET_PDEATHSIG: se o lançador morrer de repente, o caso (e o bwrap) morre junto
            libc.prctl(1, int(signal.SIGKILL), 0, 0, 0)
            if os.getppid() != pai:
                os._exit(1)
        for nome, valor in pares:
            recurso = getattr(resource, nome, None)
            if recurso is not None and valor is not None:
                duro = resource.getrlimit(recurso)[1]
                valor = valor if duro == resource.RLIM_INFINITY else min(valor, duro)
                resource.setrlimit(recurso, (valor, valor))
    return aplicar


def _virar_subreaper() -> None:
    """Linux: órfão de um caso (até o que trocou de sessão) vira filho do lançador, e não do init (idempotente)."""
    try:
        import ctypes
        ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0)  # PR_SET_CHILD_SUBREAPER
    except (OSError, AttributeError):
        pass


def _processos() -> dict[int, tuple[int, int, int, int]]:
    """Linux: pid -> (pai, grupo, uid, threads), de /proc/<pid>/stat e do dono de /proc/<pid>."""
    tabela = {}
    for nome in os.listdir("/proc"):
        if nome.isdigit():
            try:
                with open(f"/proc/{nome}/stat", "rb") as f:
                    campos = f.read().rsplit(b")", 1)[1].split()
                tabela[int(nome)] = (int(campos[1]), int(campos[2]), os.stat(f"/proc/{nome}").st_uid, int(campos[17]))
            except (OSError, IndexError, ValueError):
                continue
    return tabela


def _varrer(principal: int, antes: set[int]) -> None:
    """Mata o grupo do caso, os filhos novos do lançador (órfãos adotados) e os descendentes de todos, e recolhe os
    que forem filhos dele, até não sobrar nenhum."""
    eu = os.getpid()
    for _ in range(100):
        tabela = _processos()
        alvos = {p for p, (pai, g, *_r) in tabela.items() if g == principal or (pai == eu and p not in antes)}
        pendentes = list(alvos | {principal})
        while pendentes:
            atual = pendentes.pop()
            novos = {p for p, (pai, *_r) in tabela.items() if pai == atual} - alvos
            alvos |= novos
            pendentes += novos
        alvos -= {eu, principal}
        if not alvos:
            return
        for p in alvos:
            try:
                os.kill(p, signal.SIGKILL)
                if tabela[p][0] == eu:
                    os.waitpid(p, os.WNOHANG)
            except (ProcessLookupError, PermissionError, ChildProcessError):
                pass
        time.sleep(0.02)


# --- Windows: Job Object (estruturas como em assets/fundacao-kit/fundacao/core/processo.py) -------------------------
if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    class _ContadoresES(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in ("ReadOperationCount", "WriteOperationCount",
                    "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class _LimitesBasicos(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

    class _LimitesEstendidos(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", _LimitesBasicos), ("IoInfo", _ContadoresES),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


def _trabalho_windows(proc: subprocess.Popen, lim: dict):
    """Põe o processo, criado suspenso, num Job Object com KILL_ON_JOB_CLOSE, sem BREAKAWAY_OK e com os limites do
    plano, e só então o solta: nenhum descendente nasce fora do trabalho, e encerrar o trabalho encerra todos."""
    k32, ntdll = ctypes.WinDLL("kernel32", use_last_error=True), ctypes.WinDLL("ntdll")
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    k32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
    k32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    k32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    ntdll.NtResumeProcess.argtypes, ntdll.NtResumeProcess.restype = (wintypes.HANDLE,), ctypes.c_long
    job, info = k32.CreateJobObjectW(None, None), _LimitesEstendidos()
    # KILL_ON_JOB_CLOSE | ACTIVE_PROCESS | JOB_MEMORY | JOB_TIME | DIE_ON_UNHANDLED_EXCEPTION
    info.BasicLimitInformation.LimitFlags = 0x2000 | 0x8 | 0x200 | 0x4 | 0x400
    info.BasicLimitInformation.ActiveProcessLimit = lim["processos"]
    info.BasicLimitInformation.PerJobUserTimeLimit = lim["cpu_s"] * 10_000_000  # unidades de 100 ns
    info.JobMemoryLimit = lim["memoria_bytes"]
    if not (job and k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))  # 9 = estendidas
            and k32.AssignProcessToJobObject(job, int(proc._handle))
            and ntdll.NtResumeProcess(int(proc._handle)) == 0):
        if job:
            k32.CloseHandle(job)
        raise Recusa("o Windows recusou o Job Object que contém a árvore de processos: nada foi executado")
    return k32, job
