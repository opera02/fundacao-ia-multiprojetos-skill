"""O que um arquivo do `.git` faz o git rodar, lido como o próprio git lê (revisão de segurança da 1.7.10, KIT-F3).

O kit nunca executa git: a cópia de segurança leva o `.git` dos projetos por cópia crua (git_na_copia.RegraDaCopia) e
deixa fora o arquivo que traria credencial ou programa de volta na restauração. A conferência lia o config linha a
linha, com uma lista mais frouxa que a de scripts/git_projeto.py (hook.<x>.command, alias com ! e outras entravam), e
BOM, continuação de linha ou separador de linha do Unicode num valor escondiam a seção de verdade.
- `ler_config` lê os bytes como `git config --file X --no-includes --null --list`: BOM, CRLF, comentário, aspas,
  escape, continuação de linha, subseção nova (`[a "b"]`) e antiga (`[a.b]`) e chave na linha da seção; o que o git
  recusaria (linha ruim, BOM pela metade, escape desconhecido, aspas abertas), ou traz NUL, volta None.
- `motivo_da_chave` é cópia da de scripts/git_projeto.py (o kit não importa os scripts da skill), com o alias que
  começa por opção global do git (-c) e o lfs.extension.<x>.clean/smudge (correções da revisão 2):
  scripts/tests/test_regras_da_copia_iguais.py confere que as duas dão o mesmo resultado sobre os mesmos casos, e que
  `ler_config` dá as mesmas entradas que o git.
- `motivo_do_config` junta a ela as credenciais (URL com usuário, http.extraheader); um config que o git não leria
  fica fora sem conferir. `motivo_do_arquivo`: o `.git` arquivo (`gitdir:`) e o `commondir` que levam o git a uma
  pasta que a cópia não trata como gitdir ficam fora, e o ponteiro com caminho absoluto também (revisão 2); o tipo de
  cada arquivo e o que vale como gitdir decide a RegraDaCopia (git_na_copia.py), pela pasta e pelos HEAD da listagem.
"""

from __future__ import annotations

import os
import posixpath
import re
from pathlib import Path

_ESPACO = frozenset(b" \t\n\r")  # o isspace do git (sane_ctype): \v e \f não são espaço
_LETRA = frozenset(range(65, 91)) | frozenset(range(97, 123))
_CHAVE = _LETRA | frozenset(range(48, 58)) | {45}  # iskeychar: letra, dígito ou '-'
_ESCAPES = {116: 9, 98: 8, 110: 10, 92: 92, 34: 34}  # \t \b \n \\ \"; outro escape: o git recusa o arquivo


class _Leitor:
    """O get_next_char do git: CRLF vira LF, e o fim do arquivo vira um LF com `fim`."""

    def __init__(self, dados: bytes):
        self.dados, self.i, self.fim = dados, 0, False

    def __call__(self) -> int:
        if self.i >= len(self.dados):
            self.fim = True
            return 10
        c = self.dados[self.i]
        self.i += 1
        if c == 13 and self.dados[self.i:self.i + 1] == b"\n":
            self.i += 1
            return 10
        return c


def _baixa(c: int) -> int:
    return c + 32 if 65 <= c <= 90 else c


def ler_config(dados: bytes) -> list[tuple[str, str | None]] | None:
    """As entradas de um config do git como `git config --file X --no-includes --null --list` as daria: (seção, com a
    subseção, e nome: `secao.sub.nome`; valor ou None para chave sem `=`); None se o git recusaria o arquivo ou se ele
    traz NUL (o git cortaria o texto ali)."""
    dados = bytes(dados)
    bom = dados.startswith(b"\xef\xbb\xbf")
    if b"\0" in dados or (dados[:1] == b"\xef" and not bom):
        return None
    ler, itens, base, comentario = _Leitor(dados), [], b"", False
    ler.i = 3 if bom else 0
    while True:
        c = ler()
        if c == 10:
            if ler.fim:
                return itens
            comentario = False
        elif comentario or c in _ESPACO:
            continue
        elif c in (35, 59):  # '#' e ';'
            comentario = True
        elif c == 91:  # '['
            base = _secao(ler)
            if not base:
                return None
            base += b"."
        elif c in _LETRA:
            item = _entrada(ler, base + bytes([_baixa(c)]))
            if item is None:
                return None
            itens.append(item)
        else:
            return None


def _secao(ler: _Leitor) -> bytes | None:
    """get_base_var do git: `[secao]` e `[secao.sub]` sem caixa; `[secao "sub"]`, a subseção como está."""
    nome = bytearray()
    while True:
        c = ler()
        if ler.fim:
            return None
        if c == 93:  # ']'
            return bytes(nome)
        if c in _ESPACO:
            break
        if c not in _CHAVE and c != 46:  # '.'
            return None
        nome.append(_baixa(c))
    while c in _ESPACO:  # get_extended_base_var: espaço até a aspa, na mesma linha
        if c == 10:
            return None
        c = ler()
    if c != 34:
        return None
    nome.append(46)
    while True:
        c = ler()
        if c == 10:
            return None
        if c == 34:
            break
        if c == 92:  # a barra invertida tira o sentido do próximo
            c = ler()
            if c == 10:
                return None
        nome.append(c)
    return bytes(nome) if ler() == 93 else None


def _entrada(ler: _Leitor, nome: bytes) -> tuple[str, str | None] | None:
    """get_value do git: o resto do nome (sem caixa), espaços e, com `=`, o valor."""
    nome = bytearray(nome)
    while True:
        c = ler()
        if ler.fim or c not in _CHAVE:
            break
        nome.append(_baixa(c))
    while c in (32, 9):
        c = ler()
    valor = None
    if c != 10:
        if c != 61:  # '='
            return None
        valor = _valor(ler)
        if valor is None:
            return None
    return bytes(nome).decode("utf-8", "replace"), None if valor is None else valor.decode("utf-8", "replace")


def _valor(ler: _Leitor) -> bytes | None:
    """parse_value do git: aspas, comentário fora das aspas, escapes, continuação de linha e espaço do fim cortado."""
    valor, aspas, comentario, corte = bytearray(), False, False, 0
    while True:
        c = ler()
        if c == 10:
            return None if aspas else bytes(valor[:corte] if corte else valor)
        if comentario:
            continue
        if c in _ESPACO and not aspas:
            corte = corte or len(valor)
            if valor:
                valor.append(c)
            continue
        if not aspas and c in (35, 59):
            comentario = True
            continue
        corte = 0
        if c == 92:  # '\\'
            c = ler()
            if c == 10:
                continue  # continuação de linha: a próxima linha é parte do valor
            c = _ESCAPES.get(c)
            if c is None:
                return None
        elif c == 34:
            aspas = not aspas
            continue
        valor.append(c)


# A regra de scripts/git_projeto.py (`motivo_da_chave`, com `_partes`, `_local`, GANCHOS_VAZIO e FALSOS), copiada.
GANCHOS_VAZIO = "/dev/null"  # core.hooksPath final: /dev/null/<gancho> nunca existe no Linux
FALSOS = {"false", "no", "off", "0", ""}


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


_URL_COM_USUARIO = re.compile(r"([a-z][a-z0-9+.-]*)://([^/\s@\"'<>]+)@", re.IGNORECASE)


def _credencial(texto: str) -> bool:
    """usuário:senha@ em qualquer esquema; qualquer usuário@ em http(s) e ftp(s)."""
    return any(":" in m.group(2) or m.group(1).lower() in ("http", "https", "ftp", "ftps")
               for m in _URL_COM_USUARIO.finditer(texto))


def motivo_do_config(dados, configuracao: bool = True) -> str | None:
    """Por que um arquivo do .git fica fora da cópia (None: entra); nenhum valor sai daqui. Credencial em URL no texto
    cru; depois, lido como o git lê: credencial (URL em chave ou valor, http.extraheader) e chave que roda programa
    (`motivo_da_chave`). Um config (`configuracao`) que o git não leria fica fora sem conferir; outro arquivo que não
    se lê como config só passa pela URL."""
    bruto = dados.encode("utf-8") if isinstance(dados, str) else bytes(dados)
    if _credencial(bruto.decode("utf-8", "replace")):
        return "credencial em URL de remoto"
    itens = ler_config(bruto)
    if itens is None:
        return "config que o git não lê ou com NUL (fica fora sem conferir)" if configuracao else None
    for chave, valor in itens:
        secao, _, nome = _partes(chave)
        if _credencial(chave) or _credencial(valor or ""):
            return "credencial em URL de remoto"
        if secao == "http" and nome == "extraheader":
            return "cabeçalho de autenticação (http.extraheader)"
        if motivo_da_chave(chave, valor):
            tipo = "inclusão de outra configuração" if secao.startswith("include") else "programa configurado"
            return f"{tipo} ({secao}.{nome})"
    return None


def _absoluto(caminho: str) -> list[str]:
    """Caminho absoluto em partes, com a unidade do Windows e o /mnt/<letra> do WSL na mesma forma ('e:')."""
    texto = posixpath.normpath(caminho.replace("\\", "/"))
    m = re.match(r"([A-Za-z]):/?(.*)$", texto) or re.match(r"/mnt/([A-Za-z])(?:/(.*))?$", texto)
    partes = [m.group(1).lower() + ":", *(m.group(2) or "").split("/")] if m else ["/", *texto.split("/")]
    return [p for p in partes if p]


def _ponteiro(dados: bytes, gitfile: bool) -> str | None:
    """O caminho de um ponteiro do .git como o git lê (até o NUL, sem os \\n e \\r do fim), com /; None no `.git`
    arquivo sem `gitdir: ` (o git o recusa)."""
    texto = bytes(dados).split(b"\0", 1)[0].decode("utf-8", "replace").rstrip("\r\n")
    if gitfile and not texto.startswith("gitdir: "):
        return None
    return (texto[8:] if gitfile else texto).replace("\\", "/")


def _e_absoluto(texto: str) -> bool:
    return texto.startswith("/") or bool(re.match(r"[A-Za-z]:", texto))


def alvo_do_desvio(dados: bytes, rel: str, raiz: Path, gitfile: bool) -> str | None:
    """Para onde o `.git` arquivo (`gitdir: <caminho>`), o `commondir` ou o gitdir de worktrees/<id> (`rel`, relativo à
    raiz, com /) leva o git, como o git lê (relativo à pasta do arquivo): o caminho relativo à raiz, com /; "" se o
    arquivo não desvia (o git recusa `.git` sem `gitdir: `); None se o alvo sai da raiz."""
    texto = _ponteiro(dados, gitfile)
    if texto is None:
        return ""
    if not _e_absoluto(texto):
        alvo = posixpath.normpath(posixpath.join(posixpath.dirname(rel), texto))
        return None if alvo == ".." or alvo.startswith(("../", "/")) else alvo
    alvo = _absoluto(texto)
    for forma in {tuple(_absoluto(p)) for p in (os.path.abspath(raiz), os.path.realpath(raiz))}:
        if len(alvo) > len(forma) and [p.casefold() for p in alvo[:len(forma)]] == [p.casefold() for p in forma]:
            return "/".join(alvo[len(forma):])
    return None


ABSOLUTO = "caminho absoluto: restaurado em outra pasta, levaria o git à raiz de origem (refaça o git worktree)"


def motivo_do_arquivo(rel: str, tipo: str | None, dados: bytes | None, raiz: Path, alvo_aceito) -> str | None:
    """Por que um arquivo do .git fica fora da cópia (None: entra). `tipo`, decidido pela RegraDaCopia: "config" e
    "commondir" (num gitdir), "gitfile" (o `.git` arquivo), "gitdir" (o de worktrees/<id>) ou None (outro arquivo,
    também um ramo chamado config em refs/); `dados`: None acima do teto; `alvo_aceito(alvo, commondir)`: se o git pode
    ser levado ao `alvo`. Fica fora o ponteiro que leva o git aonde a cópia não confere config e hooks e, com caminho
    absoluto (o `git worktree add` o grava), o que na raiz restaurada levaria o commit ao repositório e aos ganchos da
    origem (revisão de segurança da 1.7.10, KIT-F3, correções das revisões 1 e 2)."""
    config, desvio = tipo == "config", tipo in ("gitfile", "commondir", "gitdir")
    if dados is None:  # acima do teto: config e ponteiros ficam fora sem conferir; o resto vai cru
        return "config grande demais para conferir" if config else "grande demais para conferir" if desvio else None
    if desvio:
        alvo = alvo_do_desvio(dados, rel, raiz, gitfile=tipo == "gitfile")
        if alvo is None or (alvo and tipo != "gitdir" and not alvo_aceito(alvo, tipo == "commondir")):
            return "leva o git a uma pasta que a cópia não confere como .git (gitdir ou commondir)"
        if alvo and _e_absoluto(_ponteiro(dados, tipo == "gitfile")):
            return ABSOLUTO
    return motivo_do_config(dados, configuracao=config)
