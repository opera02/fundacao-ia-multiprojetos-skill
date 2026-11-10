#!/usr/bin/env python3
"""Git próprio de cada projeto (escopo 0.5 da 1.7.10; desenho §5.3 e §9): o repositório do projeto é montado do
histórico copiado, sem a configuração nem os ganchos antigos, e nunca fica aninhado em outro repositório (resposta G2
do titular: "cada projeto tem seu próprio Git").

  python git_projeto.py montar   --raiz R --projeto P --de <pacote .bundle | zip do .git | pasta .git> --pasta <rel>
                                 [--autocrlf true|false|input]
  python git_projeto.py conferir --repo <pasta>
  python git_projeto.py pacote   --repo <pasta> --ramo <ramo> --saida <arquivo.bundle>

- `montar`: de um zip ou de uma pasta, monta primeiro num repositório temporário só os objetos e as referências (HEAD,
  packed-refs, shallow, objects/ sem `objects/info/alternates`, refs/) e gera um pacote (`git bundle create --all`);
  o que fica fora (config, hooks/, info/, logs/, index, modules/...) vai para `descartados`, só pelo nome. O pacote é
  conferido (`git bundle verify`, num repositório vazio) e o repositório final sai de `git clone --no-local
  --no-hardlinks` dele, com modelo vazio (nenhum gancho de exemplo). Os ramos do pacote viram ramos locais, o remoto
  do clone sai, e a configuração final é a segura: `core.hooksPath=/dev/null`, `core.fsmonitor=false` e
  `core.autocrlf` o da origem (lido do config dela como dado, sem incluir outro arquivo) ou o de `--autocrlf`. O
  `.git/info/exclude` (local: fora do histórico e do pacote; sem `.gitignore` versionado) ganha `/.porteiro/` e
  `/.cache/`, a fila do porteiro e os caches da sessão presos à raiz do repositório, onde eles ficam quando ele é a
  pasta do projeto: o `git add -A` não os leva (integração final da 1.7.10, item I7; emenda E7). Destino
  só dentro de `projects/<P>/`, novo ou vazio, sem ligação no caminho; recusa se alguma pasta acima dele, até a raiz
  do disco, tiver `.git` (o Git de um projeto não entra no da fundação, no da skill nem no de outro projeto). Montado,
  o repositório passa pela conferência do `instrucoes_aninhadas.py` (pendência do FLUXOB-B ligada na integração da
  1.7.10): `AGENTS.md`, `CLAUDE.md`, `.claude/`, `.codex/` e `.mcp.json` que um host carregaria sozinho vão para
  `instrucoes_aninhadas` e para os avisos — com o Git próprio, o Codex lê o `AGENTS.md` da raiz desse Git para baixo.
  É aviso: o código de saída não muda.
- `conferir`: acusa cada chave da configuração (`.git/config` e `config.worktree`) que aponta para comando ou para
  fora (core.hooksPath fora de /dev/null, core.fsmonitor, core.sshCommand, core.editor e core.pager, filtros,
  diff.<x>.command e textconv, merge.<x>.driver, credential.helper, include e includeIf, url.<x>.insteadOf para
  file/ext::, alias com ! ou com opção global do git como -c, lfs.extension.<x>.clean e smudge, ...) e os ganchos
  ativos em `.git/hooks`. Mostra só a chave e o motivo, nunca o valor (um credential.helper pode trazer senha). Código
  1 com achado. A regra é a mesma da cópia de segurança do kit (fundacao/core/config_git.py; teste de igualdade).
- `pacote`: o pacote de um ramo, com o histórico inteiro, para o envio pelo porteiro (`git-enviar`, desenho §2); roda
  dentro do sandbox da sessão e só com o repositório conferido.
Git sempre com ambiente saneado: GIT_CONFIG_NOSYSTEM=1, GIT_CONFIG_GLOBAL num arquivo vazio, HOME temporário,
`-c core.hooksPath=<pasta vazia>`, `-c core.fsmonitor=false` e `-c protocol.allow=never`, com o protocolo de arquivo
liberado só nos comandos que leem o pacote; o git do sistema por caminho fixo (/usr/bin/git; no Windows, o do Git for
Windows em Program Files da unidade do sistema), e só sem ele o do PATH (marcado no resultado). `safe.directory` vai
só por `-c`, nunca para a configuração global. Limite: no Windows o Git procura os ganchos em
`<unidade>:\\dev\\null\\<gancho>`; só quem grava na raiz da unidade (a sessão do Windows, sem sandbox) criaria essa
pasta: a barreira é a do Ubuntu. Saída em JSON; recusa: {"erro": ...} no stderr e código 2.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

AQUI = Path(__file__).resolve().parent
ID_PROJETO = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")  # o identificador do kit (fundacao/core/paths.py)
GANCHOS_VAZIO = "/dev/null"  # core.hooksPath final: /dev/null/<gancho> nunca existe no Linux
NAO_ANINHAR = {".git", ".claude", ".porteiro"}  # componente que a pasta do repositório não pode ter
DO_GITDIR = {"HEAD", "packed-refs", "shallow", "objects", "refs"}  # o que vem do .git de origem: objetos e referências
FORA_DOS_OBJETOS = {"objects/info/alternates", "objects/info/http-alternates"}  # objetos de outro repositório
HASH = re.compile(rb"\b([0-9a-f]{64}|[0-9a-f]{40})\b")
TEMPO_GIT = 3600
MAX_CABECALHO = 1 << 20  # cabeçalho do pacote: versão, capacidades, pré-requisitos e referências
SUBSTITUTA_DE_NOME = 0x20000000  # Windows: junção, link simbólico e afins (bit 29 da etiqueta de reparse)
FALSOS = {"false", "no", "off", "0", ""}
# O que o `.git/info/exclude` do repositório montado ignora (integração final da 1.7.10, item I7; emenda E7): a fila do
# porteiro (as respostas trazem saída do kit) e os caches da sessão (XDG_CACHE_HOME, npm, pip e uv), na raiz dele.
EXCLUSOES_LOCAIS = ("/.porteiro/", "/.cache/")
CABECALHO_DO_EXCLUDE = "# fundação de IA (git_projeto.py montar): fila do porteiro e caches da sessão, fora do Git"
TETO_EXCLUDE = 1 << 20  # o .git/info/exclude que já houver, lido até aqui


class Recusa(Exception):
    """Nada foi montado nem gravado no destino: quem chama sai com código 2 e esta mensagem."""


def _carregar(nome: str):
    """Um script ao lado deste, pelo caminho (sem mexer no `sys.path`)."""
    spec = importlib.util.spec_from_file_location(f"_git_projeto_{nome}", AQUI / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


GRAVACAO = _carregar("gravacao_segura")  # pastas e destino sem ligação, como nos outros scripts que gravam
INSTRUCOES = _carregar("instrucoes_aninhadas")  # o que um host carregaria sozinho do repositório montado
CODIGO = _carregar("codigo_do_plano")  # a citação única do comando pronto para o terminal
CODEX_NA_RAIZ = ("com o Git próprio, o Codex toma esta pasta como a raiz do projeto e lê o AGENTS.md da raiz desse Git "
                 "para baixo (até a pasta em que roda): ele vira instrução de uma sessão do Codex aberta ali dentro")
TETO_CITADOS = 50  # caminhos citados por tipo na saída do montar; acima disso, a contagem


def _e_ligacao(caminho) -> bool:
    try:
        st = os.lstat(caminho)
    except OSError:
        return False
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_reparse_tag", 0) & SUBSTITUTA_DE_NOME)


def _sha256(caminho) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def apagar(pasta) -> int:
    """Apaga a pasta (temporária ou montagem que falhou) tirando o somente leitura que o git põe nos objetos; devolve
    quantos itens sobraram (a sobra é contada, não engolida)."""
    def tirar(funcao, caminho, _erro):
        try:
            os.chmod(caminho, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
            funcao(caminho)
        except OSError:
            pass
    if not os.path.lexists(pasta):
        return 0
    if sys.version_info >= (3, 12):
        shutil.rmtree(pasta, onexc=tirar)
    else:
        shutil.rmtree(pasta, onerror=tirar)
    return sum(len(d) + len(a) for _r, d, a in os.walk(pasta)) + (1 if os.path.lexists(pasta) else 0)


# --- git com ambiente saneado ----------------------------------------------------------------------------------------
def _unidade_do_sistema() -> str:
    """Windows: a unidade da pasta de sistema, pela API (não por variável de ambiente)."""
    import ctypes
    buf = ctypes.create_unicode_buffer(260)
    n = ctypes.windll.kernel32.GetSystemDirectoryW(buf, len(buf))
    return os.path.splitdrive(buf.value)[0] if n else "C:"


def git_do_sistema() -> tuple[str, bool]:
    """(caminho do git, é o do sistema por caminho fixo). Um git posto antes no PATH não decide nada; só sem o do
    sistema vale o do PATH, e o resultado diz isso."""
    if os.name == "nt":
        base = os.path.join(_unidade_do_sistema() + os.sep, "Program Files", "Git")
        candidatos = [os.path.join(base, "cmd", "git.exe"), os.path.join(base, "bin", "git.exe")]
    else:
        candidatos = ["/usr/bin/git"]
    for candidato in candidatos:
        if os.path.isfile(candidato):
            return candidato, True
    achado = shutil.which("git")
    if not achado:
        raise Recusa("git não encontrado (nem no lugar fixo do sistema, nem no PATH): instale o git")
    return achado, False


class Git:
    """O git sem a configuração do sistema nem a do usuário, com HOME temporário, sem ganchos, sem fsmonitor e sem
    protocolo nenhum (o de arquivo só com `arquivo=True`, nos comandos que leem o pacote). Use com `with`."""

    def __init__(self) -> None:
        self.exe, self.do_sistema = git_do_sistema()
        self.base = Path(tempfile.mkdtemp(prefix="git-projeto-"))
        self.casa, self.vazia = self.base / "casa", self.base / "ganchos-vazios"
        self.casa.mkdir()
        self.vazia.mkdir()
        (self.base / "gitconfig-vazio").write_bytes(b"")
        sistema = ([os.path.join(os.environ.get("SYSTEMROOT", r"C:\Windows"), "System32"),
                    os.environ.get("SYSTEMROOT", r"C:\Windows")] if os.name == "nt" else ["/usr/bin", "/bin"])
        self.env = {"PATH": os.pathsep.join([os.path.dirname(self.exe), *sistema]), "HOME": str(self.casa),
                    "XDG_CONFIG_HOME": str(self.casa / ".config"), "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": str(self.base / "gitconfig-vazio"), "GIT_TERMINAL_PROMPT": "0",
                    "GIT_CEILING_DIRECTORIES": str(self.base), "TMPDIR": str(self.base), "TEMP": str(self.base),
                    "TMP": str(self.base), "LC_ALL": "C", "LANG": "C"}
        if os.name == "nt":
            self.env.update({k: os.environ[k] for k in ("SYSTEMROOT", "WINDIR", "COMSPEC") if k in os.environ})
            self.env["USERPROFILE"] = str(self.casa)

    def __enter__(self) -> "Git":
        return self

    def __exit__(self, *_exc) -> None:
        apagar(self.base)

    def __call__(self, *args, arquivo: bool = False, repo=None, extra: tuple = (), timeout: int = TEMPO_GIT,
                 entrada: bytes | None = None) -> subprocess.CompletedProcess:
        cfg = ["-c", f"core.hooksPath={self.vazia}", "-c", "core.fsmonitor=false", "-c", "protocol.allow=never",
               "-c", "credential.helper="]
        if arquivo:
            cfg += ["-c", "protocol.file.allow=always"]
        if repo is not None:  # só por -c: nunca na configuração global
            cfg += ["-c", f"safe.directory={Path(repo).as_posix()}"]
        try:
            return subprocess.run([self.exe, *cfg, *extra, *map(str, args)], cwd=str(self.casa), env=self.env,
                                  input=entrada, capture_output=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError) as exc:
            raise Recusa(f"o git não rodou ({type(exc).__name__}: {exc})") from None

    def exigir(self, oque: str, *args, **kw) -> str:
        r = self(*args, **kw)
        if r.returncode != 0:
            erro = r.stderr.decode("utf-8", "replace").strip()
            raise Recusa(f"git {oque} falhou (código {r.returncode}): {erro[-600:]}")
        return r.stdout.decode("utf-8", "replace")


# --- configuração: o que aponta para comando --------------------------------------------------------------------------
def ler_configuracao(git: Git, arquivo) -> list[tuple[str, str | None]]:
    """As chaves de um arquivo de configuração, lidas pelo próprio git (`config --file --no-includes --null --list`):
    a mesma leitura que o git fará depois, sem seguir include nem rodar nada. Chave sem valor: None."""
    saida = git.exigir("config (leitura)", "config", "--file", arquivo, "--no-includes", "--null", "--list")
    itens = []
    for entrada in saida.split("\0"):
        if entrada:
            chave, nova_linha, valor = entrada.partition("\n")
            itens.append((chave, valor if nova_linha else None))
    return itens


def _partes(chave: str) -> tuple[str, str, str]:
    """(seção, subseção, nome): o git escreve seção e nome em minúsculas; a subseção pode ter pontos."""
    secao, _, resto = chave.partition(".")
    sub, _, nome = resto.rpartition(".")
    return secao.lower(), sub, nome.lower()


def _local(valor: str) -> bool:
    v = valor.lower()
    return v.startswith(("ext::", "fd::", "file:", "/", "\\", ".", "~")) or bool(re.match(r"[a-z]:", v))


def motivo_da_chave(chave: str, valor: str | None) -> str | None:
    """Por que a chave roda programa (ou aponta para fora); None se não roda."""
    secao, sub, nome = _partes(chave)
    texto = "" if valor is None else valor.strip()
    par = (secao, nome)
    if par == ("core", "hookspath"):
        return None if texto == GANCHOS_VAZIO else "ganchos fora de /dev/null"
    if par == ("core", "fsmonitor"):
        return None if valor is not None and texto.lower() in FALSOS else "fsmonitor roda programa"
    if secao == "core" and nome in ("sshcommand", "editor", "pager", "askpass", "gitproxy", "alternaterefscommand"):
        return f"core.{nome} roda programa"
    if par == ("core", "worktree"):
        return "a árvore de trabalho aponta para outra pasta"
    if par in (("sequence", "editor"), ("diff", "external"), ("interactive", "difffilter"),
               ("uploadpack", "packobjectshook"), ("web", "browser"), ("sendemail", "sendmailcmd")):
        return f"{secao}.{nome} roda programa"
    if secao == "diff" and sub and nome in ("command", "textconv"):
        return f"diff.<x>.{nome} roda programa"
    if secao == "merge" and sub and nome == "driver":
        return "merge.<x>.driver roda programa"
    if secao == "filter" and nome in ("clean", "smudge", "process"):
        return f"filter.<x>.{nome} roda programa"
    if secao == "credential" and nome == "helper" and texto:
        return "credential.helper roda programa"
    if (secao, nome) == ("include", "path") or (secao == "includeif" and nome == "path"):
        return "inclui outro arquivo de configuração"
    if secao == "url" and nome in ("insteadof", "pushinsteadof") and _local(sub):
        return "url.<x>.insteadOf troca o endereço por arquivo local ou ext::"
    if secao == "gpg" and nome == "program":
        return "gpg.program roda programa"
    if secao == "gpg" and sub == "ssh" and nome == "defaultkeycommand":
        return "gpg.ssh.defaultKeyCommand roda programa"
    if secao == "tar" and nome == "command":
        return "tar.<x>.command roda programa"
    if secao == "sendemail" and nome in ("tocmd", "cccmd", "headercmd"):
        return f"sendemail.{nome} roda programa"
    if secao == "guitool" and nome == "cmd":
        return "guitool.<x>.cmd roda comando"
    if secao == "pager" and texto.lower() not in FALSOS | {"true", "yes", "on", "1"}:
        return "pager.<comando> roda programa"
    if secao == "alias" and texto.startswith("!"):
        return "alias com ! roda comando do shell"
    if secao == "alias" and texto.lstrip("\"'\\").startswith("-"):  # o git trata -c, --exec-path... como no comando
        return "alias com opção global do git (-c, --config-env, --exec-path) roda programa"
    if secao in ("difftool", "mergetool", "browser", "man") and nome in ("cmd", "path"):
        return f"{secao}.<x>.{nome} roda programa"
    if secao == "remote" and (nome in ("uploadpack", "receivepack", "vcs")
                              or (nome in ("url", "pushurl") and texto.lower().startswith(("ext::", "fd::")))):
        return f"remote.<x>.{nome} roda programa"
    if secao == "submodule" and nome == "update" and texto.startswith("!"):
        return "submodule.<x>.update com ! roda comando"
    if secao == "protocol" and nome == "allow" and (texto.lower() == "always" and not sub
                                                    or sub.lower() in ("ext", "fd") and texto.lower() != "never"):
        return "protocol.allow libera transporte que roda comando"
    if secao == "sendemail" and nome == "smtpserver" and texto.startswith("/"):
        return "sendemail.smtpserver aponta para programa"
    if secao == "trailer" and nome in ("command", "cmd"):
        return "trailer.<x>.command roda comando"
    if secao == "lfs" and sub.lower().startswith("customtransfer.") and nome == "path":
        return "lfs.customtransfer.<x>.path roda programa"
    if secao == "lfs" and sub.lower().startswith("extension.") and nome in ("clean", "smudge"):
        return f"lfs.extension.<x>.{nome} roda programa"  # o git-lfs roda no primeiro git status da raiz restaurada
    if secao == "hook" and nome == "command":
        return "hook.<x>.command roda comando"
    return None


def chaves_que_rodam(itens) -> list[dict]:
    """As chaves que rodam programa, pelo nome (subseção com cara de endereço vira <x>) e o motivo; nunca o valor."""
    return [{"chave": _chave_mostrada(chave), "motivo": motivo} for chave, valor in itens
            if (motivo := motivo_da_chave(chave, valor))]


def _gitdir(repo: Path) -> Path:
    gitdir = repo / ".git"
    if _e_ligacao(gitdir):
        raise Recusa(f"{gitdir} é ligação (link simbólico ou junção): informe a pasta real do repositório")
    if gitdir.is_file():
        raise Recusa(f"{gitdir} é um arquivo (worktree ou submódulo) que aponta para outra pasta: confira a pasta "
                     "para onde ele aponta")
    if not gitdir.is_dir():
        raise Recusa(f"{repo} não tem .git")
    if os.path.lexists(gitdir / "commondir"):
        raise Recusa(f"{gitdir}/commondir manda o git ler a configuração e os ganchos de outra pasta (worktree ou "
                     "clone com --separate-git-dir): confira a pasta comum, não esta")
    return gitdir


def conferir(repo, git: Git | None = None) -> dict:
    """Chaves que rodam programa na configuração do repositório e ganchos ativos em `.git/hooks` (só lê)."""
    if git is None:
        with Git() as novo:
            return conferir(repo, novo)
    repo = Path(os.path.abspath(repo))
    gitdir, achados = _gitdir(repo), []
    for nome in ("config", "config.worktree"):
        arquivo = gitdir / nome
        if not os.path.lexists(arquivo):
            continue
        if _e_ligacao(arquivo) or not arquivo.is_file():
            achados.append({"arquivo": nome, "motivo": "é ligação ou não é arquivo comum: não lido"})
            continue
        try:
            itens = ler_configuracao(git, arquivo)
        except Recusa as exc:
            achados.append({"arquivo": nome, "motivo": f"configuração que o git não lê: {str(exc)[:200]}"})
            continue
        achados += [{"arquivo": nome, **a} for a in chaves_que_rodam(itens)]
    ganchos = gitdir / "hooks"
    if _e_ligacao(ganchos):
        achados.append({"gancho": "hooks", "motivo": "a pasta de ganchos é ligação"})
    elif ganchos.is_dir():
        achados += [{"gancho": f"hooks/{nome}", "motivo": "gancho ativo"} for nome in sorted(os.listdir(ganchos))
                    if not nome.endswith(".sample")]
    return {"repo": str(repo), "ok": not achados, "achados": achados}


# --- montar ---------------------------------------------------------------------------------------------------------
def _pasta_relativa(texto: str) -> str:
    rel = PurePosixPath(texto.replace("\\", "/"))
    partes = rel.parts
    if (not partes or rel.is_absolute() or re.match(r"^[A-Za-z]:", texto) or any(p in ("..", ".") for p in partes)
            or texto.strip() in ("", ".")):
        raise Recusa(f"--pasta {texto!r}: use um caminho relativo dentro de projects/<projeto>/, sem '..' e sem ser a "
                     "própria pasta do projeto")
    if any(p.lower() in NAO_ANINHAR for p in partes):  # NTFS/WSL não distinguem maiúsculas: .GIT entra como .git
        raise Recusa(f"--pasta {texto!r}: o repositório não fica dentro de .git, .claude nem .porteiro")
    return rel.as_posix()


def _destino(raiz: Path, projeto: str, pasta: str) -> tuple[Path, Path, str]:
    if not ID_PROJETO.match(projeto):
        raise Recusa(f"projeto {projeto!r}: identificador inválido (minúsculas, números e hífen)")
    pasta_projeto = raiz / "projects" / projeto
    if _e_ligacao(raiz / "projects") or _e_ligacao(pasta_projeto) or not pasta_projeto.is_dir():
        raise Recusa(f"{pasta_projeto} não existe ou é ligação: o repositório só é montado dentro de um projeto")
    rel = _pasta_relativa(pasta)
    if GRAVACAO.com_ligacao(pasta_projeto, rel):
        raise Recusa(f"--pasta {rel}: o caminho passa por ligação (link simbólico ou junção)")
    destino = pasta_projeto / rel
    if os.path.lexists(destino) and (not destino.is_dir() or any(os.scandir(destino))):
        raise Recusa(f"{destino} já existe e não é uma pasta vazia: o repositório nasce numa pasta nova")
    for acima in destino.parents:
        if os.path.lexists(acima / ".git"):
            raise Recusa(f"{acima} tem .git: o repositório do projeto ficaria aninhado em outro repositório (o Git "
                         "de um projeto não entra no da fundação, no da skill nem no de outro projeto)")
    return pasta_projeto, destino, rel


def ler_cabecalho(pacote: Path) -> dict:
    """Versão, formato dos objetos, pré-requisitos e referências do pacote, lidos como texto (sem rodar o git)."""
    try:
        with open(pacote, "rb") as f:
            bruto = f.read(MAX_CABECALHO)
    except OSError as exc:
        raise Recusa(f"pacote ilegível: {pacote} ({type(exc).__name__})") from None
    fim = bruto.find(b"\n\n")
    linhas = bruto[:fim].decode("utf-8", "replace").split("\n") if fim > 0 else [""]
    versao = {"# v2 git bundle": 2, "# v3 git bundle": 3}.get(linhas[0])
    if not versao:
        raise Recusa(f"{pacote} não é um pacote do git (git bundle v2 ou v3)")
    cab = {"versao": versao, "formato": "sha1", "prerequisitos": [], "refs": []}
    for linha in linhas[1:]:
        if linha.startswith("@"):
            chave, _, valor = linha[1:].partition("=")
            if chave == "object-format":
                cab["formato"] = valor
        elif linha.startswith("-"):
            cab["prerequisitos"].append(linha[1:].split(" ")[0])
        elif linha:
            cab["refs"].append(linha.partition(" ")[2])
    if cab["formato"] not in ("sha1", "sha256"):
        raise Recusa(f"pacote com formato de objetos desconhecido: {cab['formato'][:40]}")
    if cab["prerequisitos"]:
        raise Recusa("pacote incremental (com pré-requisitos): gere na origem um pacote com o histórico inteiro "
                     "(git bundle create <arquivo> --all)")
    return cab


def _aceito(rel: str) -> bool:
    return rel.split("/", 1)[0] in DO_GITDIR and rel not in FORA_DOS_OBJETOS


def _rel_seguro(nome: str) -> str:
    rel = nome.replace("\\", "/")
    partes = rel.split("/")
    if rel.startswith("/") or re.match(r"^[A-Za-z]:", rel) or ".." in partes or "\0" in rel:
        raise Recusa(f"entrada suspeita na origem: {rel[:120]!r} (caminho absoluto ou com '..'); nada foi montado")
    return rel


def _gitdir_da_pasta(de: Path) -> Path:
    for candidato in (de, de / ".git"):
        if _e_ligacao(candidato):
            raise Recusa(f"{candidato} é ligação (link simbólico ou junção): informe a pasta real")
        if (candidato / "HEAD").is_file() and (candidato / "objects").is_dir():
            return candidato
    if (de / ".git").is_file():
        raise Recusa(f"{de / '.git'} é um arquivo (worktree ou submódulo) que aponta para outra pasta: informe a pasta "
                     "do repositório de verdade")
    raise Recusa(f"{de} não tem um .git (HEAD e objects/)")


def _copiar_sem_seguir(origem: Path, destino: Path) -> None:
    """Copia um arquivo comum sem seguir ligação (O_NOFOLLOW onde existe; arquivo trocado por ligação depois da
    listagem não é lido)."""
    fd = os.open(origem, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    with os.fdopen(fd, "rb") as fonte:
        if not stat.S_ISREG(os.fstat(fonte.fileno()).st_mode):
            raise Recusa(f"{origem} deixou de ser arquivo comum durante a cópia")
        with open(destino, "wb") as saida:
            shutil.copyfileobj(fonte, saida, 1 << 20)


def _copiar_da_pasta(gitdir: Path, alvo: Path, situacao: dict, origem_config: Path) -> None:
    for nome in sorted(os.listdir(gitdir)):
        caminho = gitdir / nome
        if nome == "config" and caminho.is_file() and not _e_ligacao(caminho):
            _copiar_sem_seguir(caminho, origem_config)  # só para ler como dado (autocrlf e o relatório)
        if nome not in DO_GITDIR:
            situacao["descartados"].append(nome)
    for pasta, subpastas, arquivos in os.walk(gitdir):
        atual = Path(pasta)
        rel_pasta = atual.relative_to(gitdir).as_posix()
        for nome in list(subpastas):
            rel = nome if rel_pasta == "." else f"{rel_pasta}/{nome}"
            if _e_ligacao(atual / nome) or not _aceito(rel):
                subpastas.remove(nome)
                if _e_ligacao(atual / nome) and _aceito(rel):
                    situacao["avisos"].append(f"{rel}: ligação não seguida")
        for nome in arquivos:
            rel = nome if rel_pasta == "." else f"{rel_pasta}/{nome}"
            if not _aceito(rel):
                if rel in FORA_DOS_OBJETOS:
                    situacao["descartados"].append(rel)
                continue
            if _e_ligacao(atual / nome):
                situacao["avisos"].append(f"{rel}: ligação não seguida")
                continue
            destino = alvo / rel
            destino.parent.mkdir(parents=True, exist_ok=True)
            _copiar_sem_seguir(atual / nome, destino)


def _copiar_do_zip(zip_: Path, alvo: Path, situacao: dict, origem_config: Path) -> None:
    try:
        zf = zipfile.ZipFile(zip_)
    except (OSError, zipfile.BadZipFile) as exc:
        raise Recusa(f"zip ilegível: {zip_} ({type(exc).__name__})") from None
    with zf:
        membros = {_rel_seguro(info.filename): info for info in zf.infolist()}
        prefixos = sorted({n[:-4] for n in membros if n == "HEAD" or n.endswith("/HEAD")}, key=len)
        prefixo = next((p for p in prefixos if any(n.startswith(p + "objects/") for n in membros)), None)
        if prefixo is None:
            raise Recusa(f"{zip_} não tem um .git (HEAD e objects/)")
        topo = set()
        for nome, info in sorted(membros.items()):
            if not nome.startswith(prefixo) or nome.endswith("/"):
                continue
            rel = nome[len(prefixo):]
            if rel == "config":
                with zf.open(info) as fonte, open(origem_config, "wb") as saida:
                    shutil.copyfileobj(fonte, saida)
            if not _aceito(rel):
                topo.add(rel if rel in FORA_DOS_OBJETOS else rel.split("/", 1)[0])
                continue
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                situacao["avisos"].append(f"{rel}: ligação no zip, não extraída")
                continue
            destino = alvo / rel
            destino.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as fonte, open(destino, "wb") as saida:
                shutil.copyfileobj(fonte, saida, 1 << 20)
        situacao["descartados"] += sorted(topo)


def _formato_dos_objetos(gitdir: Path) -> str:
    """sha1 ou sha256, pelo tamanho do primeiro hash em HEAD, packed-refs ou refs/ (o config da origem é dado)."""
    candidatos = [gitdir / "HEAD", gitdir / "packed-refs"]
    for pasta, _sub, arquivos in os.walk(gitdir / "refs"):
        candidatos += [Path(pasta) / a for a in sorted(arquivos)]
    for arquivo in candidatos:
        try:
            achado = HASH.search(arquivo.read_bytes()[:65536])
        except OSError:
            continue
        if achado:
            return "sha256" if len(achado.group(1)) == 64 else "sha1"
    return "sha1"


def _head_valido(git: Git, head: str) -> bool:
    """O HEAD da origem: commit solto (40/64 dígitos hex) ou `ref: refs/...` que o próprio Git saneado aceita
    (`git check-ref-format`). Pelo Git, e não por um regex mais estrito, para um ramo com acento (provável para o
    titular) não ser recusado e trocado por master."""
    texto = head.strip()
    if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", texto):
        return True
    if not texto.startswith("ref: "):
        return False
    ref = texto[len("ref: "):].strip()
    if not ref.startswith("refs/") or ref.startswith("-") or any(ord(c) < 0x20 or c == "\x7f" for c in ref):
        return False
    return git("check-ref-format", ref).returncode == 0


def _pacote_da_origem(git: Git, de: Path, tipo: str, situacao: dict) -> tuple[Path, Path | None]:
    """De um zip ou de uma pasta: monta só objetos e referências num repositório temporário e gera o pacote."""
    origem_config = git.base / "origem.config"
    bruto = git.base / "bruto"
    bruto.mkdir()
    if tipo == "zip":
        _copiar_do_zip(de, bruto, situacao, origem_config)
    else:
        _copiar_da_pasta(_gitdir_da_pasta(de), bruto, situacao, origem_config)
    if (bruto / "reftable").exists() or "reftable" in situacao["descartados"]:
        raise Recusa("a origem usa o formato reftable: gere na origem um pacote (git bundle create <arquivo> --all) "
                     "e monte a partir dele")
    montagem = git.base / "montagem.git"
    git.exigir("init", "init", "--bare", "-q", f"--template={git.vazia}",
               f"--object-format={_formato_dos_objetos(bruto)}", montagem)
    for pasta, _sub, arquivos in os.walk(bruto):
        for nome in arquivos:
            origem = Path(pasta) / nome
            destino = montagem / origem.relative_to(bruto)
            destino.parent.mkdir(parents=True, exist_ok=True)
            os.replace(origem, destino)  # a mesma pasta temporária: só troca o nome
    head = (montagem / "HEAD").read_bytes().decode("utf-8", "replace") if (montagem / "HEAD").is_file() else ""
    if not _head_valido(git, head):
        (montagem / "HEAD").write_bytes(b"ref: refs/heads/master\n")
        situacao["avisos"].append("HEAD da origem fora do formato: trocado por refs/heads/master")
    pacote = git.base / "origem.bundle"
    git.exigir("bundle create", "--git-dir", montagem, "bundle", "create", pacote, "--all")
    return pacote, origem_config if origem_config.is_file() else None


def _tipo_da_origem(de: Path) -> str:
    if _e_ligacao(de):
        raise Recusa(f"--de {de}: é ligação (link simbólico ou junção); informe o caminho real")
    if de.is_dir():
        return "pasta"
    if not de.is_file():
        raise Recusa(f"--de {de}: não existe")
    with open(de, "rb") as f:
        inicio = f.read(16)
    if inicio.startswith((b"# v2 git bundle", b"# v3 git bundle")):
        return "pacote"
    if zipfile.is_zipfile(de):
        return "zip"
    raise Recusa(f"--de {de}: não é pacote do git (.bundle), zip do .git nem pasta")


def _chave_mostrada(chave: str) -> str:
    """A chave para o relatório: subseção com cara de endereço (pode trazer usuário e senha) vira <x>."""
    secao, sub, nome = _partes(chave)
    if sub and any(marca in sub for marca in ("://", "@", ":", "/", "\\")):
        sub = "<x>"
    return ".".join(p for p in (secao, sub, nome) if p)


def _da_origem(git: Git, origem_config: Path, origem: dict, situacao: dict) -> str | None:
    """O config da origem, lido como dado: as chaves que ficaram de fora (só o nome) e o core.autocrlf dela."""
    try:
        itens = ler_configuracao(git, origem_config)
    except Recusa:
        situacao["avisos"].append("configuração da origem ilegível pelo git: ignorada")
        return None
    origem["configuracao_descartada"] = sorted({_chave_mostrada(c) for c, _v in itens})
    origem["que_rodaria_programa"] = sorted({_chave_mostrada(a["chave"]) for a in chaves_que_rodam(itens)})
    valores = [v for c, v in itens if c.lower() == "core.autocrlf"]
    valor = valores[-1] if valores else None  # chave repetida: o git usa o último valor
    if valor is None:
        return None
    v = valor.strip().lower()
    v = {"yes": "true", "on": "true", "1": "true", "no": "false", "off": "false", "0": "false"}.get(v, v)
    return v if v in ("true", "false", "input") else None


def _esvaziar(pasta: Path) -> None:
    for item in os.listdir(pasta) if pasta.is_dir() else []:
        alvo = pasta / item
        if alvo.is_dir() and not _e_ligacao(alvo):
            apagar(alvo)
        else:
            os.chmod(alvo, stat.S_IWRITE | stat.S_IREAD)
            os.unlink(alvo)


def montar(raiz, projeto: str, de, pasta: str, autocrlf: str | None = None) -> dict:
    raiz, de = Path(os.path.abspath(raiz)), Path(os.path.abspath(de))
    pasta_projeto, destino, rel = _destino(raiz, projeto, pasta)
    tipo = _tipo_da_origem(de)
    if de.is_relative_to(destino):
        raise Recusa("--de fica dentro do destino")
    situacao = {"descartados": [], "avisos": []}
    criado = not os.path.lexists(destino)
    with Git() as git:
        try:
            if tipo == "pacote":
                pacote, origem_config = de, None
            else:
                pacote, origem_config = _pacote_da_origem(git, de, tipo, situacao)
            cab = ler_cabecalho(pacote)
            origem = {"tipo": tipo, "caminho": str(de), "pacote_sha256": _sha256(pacote)}
            da_origem = _da_origem(git, origem_config, origem, situacao) if origem_config else None
            autocrlf = autocrlf or da_origem
            verificar = git.base / "verificar.git"
            git.exigir("init", "init", "--bare", "-q", f"--template={git.vazia}", f"--object-format={cab['formato']}",
                       verificar)
            git.exigir("bundle verify", "--git-dir", verificar, "bundle", "verify", pacote, arquivo=True)
            if "/" in rel:
                GRAVACAO.pasta_sem_ligacao(pasta_projeto, rel.rpartition("/")[0])
            extra = ("-c", f"core.autocrlf={autocrlf}") if autocrlf else ()
            r = git("clone", "--no-local", "--no-hardlinks", f"--template={git.vazia}", pacote, destino,
                    arquivo=True, extra=extra)
            if r.returncode != 0:
                raise Recusa("git clone falhou: " + r.stderr.decode("utf-8", "replace").strip()[-600:])
            situacao["avisos"] += [linha.strip() for linha in r.stderr.decode("utf-8", "replace").splitlines()
                                   if linha.strip().lower().startswith("warning")]
            resultado = _acertar(git, destino, autocrlf, situacao)
        except BaseException:
            if criado:
                apagar(destino)
            else:
                _esvaziar(destino)
            raise
    instrucoes, avisos = instrucoes_do_repositorio(destino, rel)
    return {"repositorio": str(destino), "projeto": projeto, "origem": origem, **resultado,
            "descartados": sorted(set(situacao["descartados"])), "avisos": situacao["avisos"] + avisos,
            "instrucoes_aninhadas": instrucoes, "git": {"caminho": git.exe, "do_sistema": git.do_sistema}}


def conferir_de_novo(destino: Path) -> str:
    """O passo de rodar de novo a conferência das instruções aninhadas no repositório: o comando pronto, com cada
    caminho citado para o shell de destino (`codigo_do_plano.citar_no_terminal`), em vez de entre aspas duplas, em que
    `$` e a crase valem [terceira revisão do pacote INTEG-FLUXOB]; sem comando pronto se um deles não dá para citar
    com segurança."""
    try:
        return (f"rode {'python' if os.name == 'nt' else 'python3'} -I -B "
                f"{CODIGO.citar_no_terminal(AQUI / 'instrucoes_aninhadas.py')} listar --raiz "
                f"{CODIGO.citar_no_terminal(destino)}")
    except ValueError as exc:
        return (f"rode o instrucoes_aninhadas.py listar nesta pasta (não há comando pronto: {exc}, e o comando não o "
                "cita com segurança no terminal; renomeie a pasta)")


def _mostrado(caminho: str) -> str:
    """Um caminho vindo do repositório, para o aviso: sem controle nem caractere invisível (FLUXB-F3, revisão 2)."""
    return "".join(c if c.isprintable() else "?" for c in caminho)


def instrucoes_do_repositorio(destino: Path, rel: str) -> tuple[dict, list[str]]:
    """A conferência do `instrucoes_aninhadas.py` no repositório montado (só lê, sem rodar nada): o que um host
    carregaria sozinho dali — `AGENTS.md`, `CLAUDE.md`, `.claude/`, `.codex/` e `.mcp.json` — e os avisos para a saída.
    `rel`: a pasta do repositório relativa ao projeto (fora de `data/`, o `claudeMdExcludes` dos perfis do host não a
    cobre). Se a conferência não roda, o resumo tem as mesmas chaves, vazias, e o `erro` [revisão do pacote
    INTEG-FLUXOB]; ela não rodou ou ficou parcial: o aviso traz o passo de rodá-la de novo (`conferir_de_novo`).
    A `.git` da raiz é a do clone que o montar acabou de fazer: só ela fica fora da conferência sem registro; a skill
    com nome fora do padrão ou incerto ganha aviso com as pastas a neutralizar, e o parcial diz as pastas puladas
    (revisão de segurança da 1.7.10, FLUXB-F3, revisão 2)."""
    try:
        res = INSTRUCOES.listar(destino, git_da_raiz_confiavel=True)
    except (OSError, ValueError) as exc:
        return ({"encontrados": None, "completo": False, "contagem": {}, "itens": {},
                 "negar_skills": [], "negar_agentes": [], "nomes_fora_do_padrao": [], "ligacoes_nao_seguidas": 0, "nao_lidos": 0, "erro": type(exc).__name__,
                 "codex": CODEX_NA_RAIZ},
                [f"a conferência das instruções aninhadas não rodou ({type(exc).__name__}): "
                 f"{conferir_de_novo(destino)} antes de abrir uma sessão ali"])
    itens = {tipo: [i["caminho"] for i in lista] for tipo, lista in res["itens"].items() if lista}
    resumo = {"encontrados": res["encontrados"], "completo": res["completo"],
              "contagem": {tipo: len(caminhos) for tipo, caminhos in itens.items()},
              "itens": {tipo: caminhos[:TETO_CITADOS] for tipo, caminhos in itens.items()},
              "negar_skills": res["sugestoes"]["negar_skills"],
              "negar_agentes": res["sugestoes"]["negar_agentes"], "nomes_fora_do_padrao": res["nomes_fora_do_padrao"],
              "ligacoes_nao_seguidas": len(res["ligacoes_nao_seguidas"]), "nao_lidos": len(res["nao_lidos"]),
              "codex": CODEX_NA_RAIZ}
    avisos = []
    if res["encontrados"]:
        tipos = ", ".join(f"{tipo} ({n})" for tipo, n in resumo["contagem"].items())
        aviso = (f"o repositório traz arquivos que o Claude Code ou o Codex carregam sozinhos ({tipos}; AGENTS.md, "
                 "CLAUDE.md, .claude/, .codex/ e .mcp.json): vieram da origem e são dado, não instrução, até o titular "
                 f"decidir; {CODEX_NA_RAIZ}")
        if rel.split("/")[0] != "data":  # com a caixa exata: `Data/` não é garantida pelo padrão **/projects/*/data/**
            aviso += ("; fora de data/, o claudeMdExcludes dos perfis do host não cobre esta pasta: o CLAUDE.md e o "
                      "AGENTS.md dela carregam quando a sessão ler um arquivo dali")
        if resumo["negar_skills"]:
            aviso += ("; negue as skills dele no preparo do host: --negar-skill "
                      + " --negar-skill ".join(resumo["negar_skills"]))
        if resumo["negar_agentes"]:
            aviso += ("; negue os agentes dele: --negar-agente "
                      + " --negar-agente ".join(resumo["negar_agentes"]))
        avisos.append(aviso)
    if res["nomes_fora_do_padrao"]:  # FLUXB-F3, revisão 2
        pastas = sorted({_mostrado(i["pasta"]) for i in res["nomes_fora_do_padrao"]})
        avisos.append(f"skills com nome fora do padrão do preparo do host ou incerto ({len(pastas)}): a negação pelo "
                      "nome pode não cobri-las; antes de abrir uma sessão ali, neutralize estas pastas do repositório "
                      "(tire-as dele, como o importar.py faz com .claude/skills): " + ", ".join(pastas[:TETO_CITADOS]))
    if not res["completo"]:
        puladas = [_mostrado(n["caminho"]) for n in res["nao_lidos"] if n["motivo"].startswith("pasta pulada")]
        avisos.append("a conferência das instruções aninhadas ficou parcial (ligação não seguida, teto, arquivo não "
                      "lido ou pasta pulada"
                      + (f": {', '.join(puladas[:TETO_CITADOS])} não foram conferidas" if puladas else "")
                      + f"): para conferir, {conferir_de_novo(destino)}")
    return resumo, avisos


def _ler_exclude(arquivo: Path) -> bytes:
    """O `.git/info/exclude` que já houver, sem seguir ligação (lstat antes, O_NOFOLLOW onde existe, fstat e o mesmo
    arquivo depois) e até `TETO_EXCLUDE`; ausente: vazio."""
    try:
        antes = os.lstat(arquivo)
    except FileNotFoundError:
        return b""
    if _e_ligacao(arquivo) or not stat.S_ISREG(antes.st_mode):
        raise Recusa(f"{arquivo} é ligação ou não é arquivo comum: nada foi gravado nele")
    fd = os.open(arquivo, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    with os.fdopen(fd, "rb") as fonte:
        aberto = os.fstat(fonte.fileno())
        if not stat.S_ISREG(aberto.st_mode) or (aberto.st_dev, aberto.st_ino) != (antes.st_dev, antes.st_ino):
            raise Recusa(f"{arquivo} foi trocado durante a leitura: nada foi gravado nele")
        dados = fonte.read(TETO_EXCLUDE + 1)
    if len(dados) > TETO_EXCLUDE:
        raise Recusa(f"{arquivo} passa de {TETO_EXCLUDE} bytes: nada foi gravado nele")
    return dados


def gravar_exclusoes(destino: Path) -> list[str]:
    """Põe `EXCLUSOES_LOCAIS` no `.git/info/exclude` do repositório (integração final da 1.7.10, item I7; emenda E7):
    local, sem `.gitignore` versionado, o histórico e o pacote não mudam e o que o histórico já tem continua visto (o
    exclude só vale para o que não é rastreado). Presas à raiz (`/`): a mesma pasta mais abaixo continua sendo do
    código. Sem seguir ligação (`gravacao_segura`: a pasta e o arquivo, por temporário e troca de nome); o que já
    houver no arquivo fica, e a linha que já está não se repete. Devolve as linhas."""
    arquivo = GRAVACAO.pasta_sem_ligacao(destino, ".git/info") / "exclude"
    atual = _ler_exclude(arquivo)
    linhas = {linha.strip() for linha in atual.decode("utf-8", "replace").splitlines()}
    faltam = [linha for linha in EXCLUSOES_LOCAIS if linha not in linhas]
    if faltam:
        inicio = atual + (b"\n" if atual and not atual.endswith(b"\n") else b"")
        GRAVACAO.publicar(arquivo, inicio + "\n".join([CABECALHO_DO_EXCLUDE, *faltam, ""]).encode("utf-8"))
    return list(EXCLUSOES_LOCAIS)


def _acertar(git: Git, destino: Path, autocrlf: str | None, situacao: dict) -> dict:
    """Ramos do pacote viram locais, o remoto do clone sai e a configuração fica a segura, com a fila do porteiro e os
    caches da sessão no exclude local (`gravar_exclusoes`); confere no fim."""
    remotos = git.exigir("for-each-ref", "-C", destino, "for-each-ref", "--format=%(refname)", "refs/remotes/origin/",
                         repo=destino).split()
    locais = set(git.exigir("for-each-ref", "-C", destino, "for-each-ref", "--format=%(refname)", "refs/heads/",
                            repo=destino).split())
    for ref in remotos:
        nome = ref[len("refs/remotes/origin/"):]
        if nome != "HEAD" and f"refs/heads/{nome}" not in locais:
            git.exigir("update-ref", "-C", destino, "update-ref", f"refs/heads/{nome}", ref, repo=destino)
    git.exigir("remote remove", "-C", destino, "remote", "remove", "origin", repo=destino)
    git.exigir("config", "-C", destino, "config", "core.hooksPath", GANCHOS_VAZIO, repo=destino)
    git.exigir("config", "-C", destino, "config", "core.fsmonitor", "false", repo=destino)
    if autocrlf:
        git.exigir("config", "-C", destino, "config", "core.autocrlf", autocrlf, repo=destino)
    if (destino / ".git" / "hooks").is_dir():
        apagar(destino / ".git" / "hooks")
    exclusoes = gravar_exclusoes(destino)
    ramos = git.exigir("for-each-ref", "-C", destino, "for-each-ref", "--format=%(refname:short)", "refs/heads/",
                       repo=destino).split()
    etiquetas = git.exigir("for-each-ref", "-C", destino, "for-each-ref", "--format=%(refname:short)", "refs/tags/",
                           repo=destino).split()
    head = git("-C", destino, "symbolic-ref", "-q", "--short", "HEAD", repo=destino).stdout.decode().strip() or None
    if head is None:
        situacao["avisos"].append("HEAD sem ramo (solto ou ausente no pacote): confira o checkout")
    atributos = destino / ".gitattributes"
    if atributos.is_file() and "filter=lfs" in atributos.read_text(encoding="utf-8", errors="replace"):
        situacao["avisos"].append("arquivos do Git LFS ficaram como ponteiros: o filtro não roda aqui")
    if (destino / ".gitmodules").is_file():
        situacao["avisos"].append("submódulos não montados: cada um precisa do próprio pacote")
    conf = conferir(destino, git)
    if not conf["ok"]:
        raise Recusa("o repositório montado não passou na conferência: " + json.dumps(conf["achados"],
                                                                                     ensure_ascii=False)[:600])
    return {"ramos": ramos, "etiquetas": len(etiquetas), "head": head,
            "configuracao": {"core.hooksPath": GANCHOS_VAZIO, "core.fsmonitor": "false",
                             "core.autocrlf": autocrlf or "não definido (a origem não trouxe e --autocrlf faltou)",
                             ".git/info/exclude": exclusoes},
            "conferencia": conf}


# --- pacote para o envio ---------------------------------------------------------------------------------------------
def pacote(repo, ramo: str, saida) -> dict:
    repo, saida = Path(os.path.abspath(repo)), Path(os.path.abspath(saida))
    if not ramo or ramo.startswith("-") or any(ord(c) < 0x20 or c == "\x7f" for c in ramo):
        raise Recusa(f"--ramo {ramo!r}: nome inválido (vazio, começa com '-' ou tem caractere de controle); o resto "
                     "quem decide é o git (check-ref-format --branch), que aceita ramo com acento")
    if saida.suffix != ".bundle":
        raise Recusa("--saida termina em .bundle")
    gitdir = _gitdir(repo)
    if saida.is_relative_to(gitdir):
        raise Recusa("--saida fica fora do .git")
    with Git() as git:
        conf = conferir(repo, git)
        if not conf["ok"]:
            achados = (a.get("chave") or a.get("gancho") or a.get("arquivo", "") for a in conf["achados"])
            raise Recusa("a configuração ou os ganchos do repositório rodariam programas; conserte e confira de novo: "
                         + "; ".join(achados))
        git.exigir("check-ref-format", "check-ref-format", "--branch", ramo)
        r = git("-C", repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{ramo}^{{commit}}", repo=repo)
        commit = r.stdout.decode("utf-8", "replace").strip()
        if r.returncode != 0 or not commit:
            raise Recusa(f"o ramo {ramo} não existe em {repo}")
        formato = git.exigir("rev-parse", "-C", repo, "rev-parse", "--show-object-format", repo=repo).strip() or "sha1"
        saida.parent.mkdir(parents=True, exist_ok=True)
        GRAVACAO.conferir_destino(saida)
        tmp = saida.with_name(f".{saida.name}.{os.getpid()}.tmp")
        try:
            git.exigir("bundle create", "-C", repo, "bundle", "create", tmp, f"refs/heads/{ramo}", repo=repo)
            verificar = git.base / "verificar.git"
            git.exigir("init", "init", "--bare", "-q", f"--template={git.vazia}", f"--object-format={formato}",
                       verificar)
            git.exigir("bundle verify", "--git-dir", verificar, "bundle", "verify", tmp, arquivo=True)
            GRAVACAO.conferir_destino(saida)
            os.replace(tmp, saida)
        finally:
            if os.path.lexists(tmp):
                os.unlink(tmp)
    return {"bundle": str(saida), "sha256": _sha256(saida), "tamanho": saida.stat().st_size, "ramo": ramo,
            "commit": commit, "repo": str(repo), "git": {"caminho": git.exe, "do_sistema": git.do_sistema}}


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("montar", help="monta o repositório do projeto a partir do histórico copiado")
    m.add_argument("--raiz", type=Path, required=True)
    m.add_argument("--projeto", required=True)
    m.add_argument("--de", type=Path, required=True, help="pacote .bundle, zip do .git ou pasta .git copiada")
    m.add_argument("--pasta", required=True, help="pasta do repositório, relativa a projects/<projeto>/")
    m.add_argument("--autocrlf", choices=["true", "false", "input"], help="core.autocrlf (padrão: o da origem)")
    c = sub.add_parser("conferir", help="acusa configuração que roda programa e ganchos ativos")
    c.add_argument("--repo", type=Path, required=True)
    p = sub.add_parser("pacote", help="pacote de um ramo para o envio pelo porteiro")
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--ramo", required=True)
    p.add_argument("--saida", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        if args.cmd == "montar":
            res = montar(args.raiz, args.projeto, args.de, args.pasta, args.autocrlf)
        elif args.cmd == "conferir":
            res = conferir(args.repo)
        else:
            res = pacote(args.repo, args.ramo, args.saida)
    except (Recusa, OSError) as exc:
        print(json.dumps({"erro": f"{exc}; nada foi alterado no destino"}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 1 if args.cmd == "conferir" and not res["ok"] else 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
