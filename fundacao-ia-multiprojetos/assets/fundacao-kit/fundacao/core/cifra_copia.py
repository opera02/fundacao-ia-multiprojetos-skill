"""Invólucro do GnuPG para a cópia de segurança cifrada (1.7.11; desenho DESENHO-COPIA-CIFRADA-1.7.11, lote 1, e a medida
MEDIDA-GPG-20261108). Só biblioteca padrão mais o `gpg` por CAMINHO FIXO (como o ssh-keygen em decisoes.py): no Windows,
o do Git para Windows; no Ubuntu, /usr/bin/gpg. Um `gpg` posto antes no PATH não vale.

O que a medida de 08/11/2026 mudou no desenho (GnuPG 2.4.9 do Git):
- Sem OCB: `--force-ocb` e afins respondem "is not considered an option". A cifra é SEIPD v1 (tag 18, MDC), AES-256. O MDC
  cobre a parte inteira e o `gpg --decrypt` entrega o claro ANTES de conferi-lo (rc 2 no fim): quem decifrar só usa o que
  saiu com rc 0 — a parte é a unidade que se descarta.
- É um `gpg` de msys: caminho do Windows (`C:\\...`) é lido como relativo; vale `/c/...` (`para_gpg`). E o `--homedir`
  precisa de até ~85 caracteres nessa forma, senão o soquete do agente não nasce (decifrar e criar chave; cifrar com
  `--no-keyring` não usa agente).
- `--list-packets` de um prefixo sai com rc 2: os cabeçalhos dos pacotes são lidos aqui (`conferir_cabecalho`), sem `gpg`.

A chave pública é lida UMA vez (arquivo comum, sem ligação, até 1 MiB) e a cópia gravada num --homedir temporário vazio é a
que se confere e a que cifra: nada de chave privada nem de chaveiro nesse --homedir. Quem chama garante que o arquivo vem
da âncora protegida (conferir_ancora, no lote da CLI). Texto claro só passa pelo pipe do processo: o claro nunca é gravado.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path

from . import limpeza, preparo
from .contracts import FundacaoError

GPG_WINDOWS = r"C:\Program Files\Git\usr\bin\gpg.exe"
GPG_LINUX = "/usr/bin/gpg"
VERSAO_MINIMA = (2, 4)
TETO_CHAVE = 1 << 20
PREFIXO = 65536  # bytes do início de cada parte que a conferência sem senha lê
_BLOCO = 1 << 20
_SEM_JANELA = 0x08000000 if os.name == "nt" else 0
_VERSAO = re.compile(r"^gpg \(GnuPG[^)]*\) (\d+)\.(\d+)\.(\d+)")
_INVALIDAS = {"r", "e", "i", "d"}  # revogada, vencida, inválida, desabilitada


class CifraRecusada(FundacaoError):
    """O `gpg` ou a chave não servem, ou a cifra falhou: nenhuma cópia cifrada foi promovida."""

    code = "E_CIFRA"


def gpg_do_sistema() -> str | None:
    """Caminho fixo do gpg, se existir; nunca o PATH."""
    caminho = Path(GPG_WINDOWS if os.name == "nt" else GPG_LINUX)
    return str(caminho) if caminho.is_file() else None


def _ambiente() -> dict:
    """Ambiente sem GNUPGHOME, GPG_AGENT_INFO e afins: o --homedir vai sempre pela linha de comando."""
    return {k: v for k, v in os.environ.items() if not k.upper().startswith(("GNUPG", "GPG"))}


def versao_gpg(exe: str) -> tuple[int, int, int]:
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, timeout=30, env=_ambiente(),
                           creationflags=_SEM_JANELA)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CifraRecusada("não foi possível rodar o gpg para ler a versão", gpg=str(exe), erro=type(exc).__name__) from exc
    linhas = r.stdout.decode("utf-8", "replace").splitlines()
    achou = _VERSAO.match(linhas[0]) if linhas else None
    if not achou:
        raise CifraRecusada("a saída de `gpg --version` não é a de um GnuPG", gpg=str(exe))
    return tuple(int(n) for n in achou.groups())


def localizar_gpg(exe: str | None = None) -> dict:
    """{"exe", "versao"} do gpg de caminho fixo (ou do `exe` dado, só nos testes), versão mínima 2.4; senão CifraRecusada."""
    exe = exe or gpg_do_sistema()
    if not exe or not Path(exe).is_file():
        raise CifraRecusada("gpg não encontrado no caminho fixo (Git para Windows ou /usr/bin/gpg): nenhuma cópia cifrada "
                            "foi feita", caminho=GPG_WINDOWS if os.name == "nt" else GPG_LINUX)
    versao = versao_gpg(exe)
    if versao[:2] < VERSAO_MINIMA:
        raise CifraRecusada(f"gpg {'.'.join(map(str, versao))} é anterior ao 2.4 exigido: nenhuma cópia cifrada foi feita",
                            versao=".".join(map(str, versao)))
    return {"exe": str(exe), "versao": ".".join(map(str, versao))}


def para_gpg(caminho) -> str:
    """Caminho no formato que o gpg entende: no Windows (gpg de msys), `C:\\a\\b` vira `/c/a/b`; UNC não foi medido."""
    p = os.path.abspath(caminho)
    if os.name != "nt":
        return p
    if len(p) < 3 or p[1] != ":":
        raise CifraRecusada("caminho sem letra de unidade (compartilhamento de rede não foi medido com o gpg do Git)",
                            caminho=p)
    return "/" + p[0].lower() + p[2:].replace("\\", "/")


def _ler_chave(colunas: str) -> dict:
    """Principal e subchaves de cifra válidas da saída `--with-colons` de `--show-keys`; chave privada ou arquivo com mais
    de uma chave pública: CifraRecusada."""
    chaves, atual = [], None
    for linha in colunas.splitlines():
        c = linha.split(":")
        if c[0] in ("sec", "ssb"):
            raise CifraRecusada("o arquivo da chave tem material PRIVADO (sec/ssb): informe só a chave pública")
        if c[0] in ("pub", "sub") and len(c) > 11:
            atual = {"tipo": c[0], "valida": c[1] not in _INVALIDAS, "cifra": "e" in c[11] and "D" not in c[11], "fpr": None}
            chaves.append(atual)
        elif c[0] == "fpr" and atual is not None and atual["fpr"] is None and len(c) > 9:
            atual["fpr"] = c[9].upper()
    pubs = [k for k in chaves if k["tipo"] == "pub"]
    if len(pubs) != 1 or not pubs[0]["fpr"]:
        raise CifraRecusada("o arquivo da chave precisa ter exatamente uma chave pública OpenPGP")
    if not pubs[0]["valida"]:
        raise CifraRecusada("a chave pública está revogada, vencida ou inválida")
    cifra = [k["fpr"] for k in chaves if k["cifra"] and k["valida"] and k["fpr"]]
    if not cifra:
        raise CifraRecusada("a chave pública não tem subchave de cifra válida")
    return {"principal": pubs[0]["fpr"], "subchaves_de_cifra": cifra}


def ids_do_destinatario(destinatario: dict) -> set[str]:
    """Os `keyid` (64 bits finais da impressão digital) que o pacote de chave de sessão de uma parte pode trazer."""
    return {f[-16:].upper() for f in destinatario["subchaves_de_cifra"]}


class SessaoDeCifra:
    """Chave pública conferida e --homedir temporário vazio, valendo até o `with` acabar (a limpeza é contada)."""

    def __init__(self, chave_publica, exe: str | None = None):
        self.gpg = localizar_gpg(exe)
        caminho = Path(chave_publica)
        if preparo.ligacao_no_caminho(caminho):
            raise CifraRecusada("a chave pública passa por ligação (link simbólico ou junção): informe o caminho real")
        if not caminho.is_file() or caminho.stat().st_size > TETO_CHAVE:
            raise CifraRecusada("chave pública ausente, que não é arquivo comum ou maior que 1 MiB", chave=str(caminho))
        bruto = preparo.ler(caminho)
        self.casa = Path(tempfile.mkdtemp(prefix="gc"))
        self.chave = self.casa / "chave.asc"
        self.sobra: dict = {}
        try:
            with open(self.chave, "xb") as saida:
                saida.write(bruto)
            r = subprocess.run(self.argumentos("--no-keyring", "--show-keys", "--with-colons", "--fixed-list-mode",
                                               para_gpg(self.chave)), capture_output=True, timeout=60,
                               env=_ambiente(), creationflags=_SEM_JANELA)
            if r.returncode != 0:
                raise CifraRecusada("o gpg não leu a chave pública", codigo_gpg=r.returncode,
                                    saida_gpg=r.stderr.decode("utf-8", "replace")[:300])
            self.destinatario = _ler_chave(r.stdout.decode("utf-8", "replace"))
        except BaseException:
            self.sobra = limpeza.limpar(self.casa, self.casa.parent)
            raise

    def argumentos(self, *resto: str) -> list[str]:
        return [self.gpg["exe"], "--no-options", "--batch", "--no-tty", "--quiet", "--homedir", para_gpg(self.casa), *resto]

    def cifrador(self, saida) -> "Cifrador":
        return Cifrador(self, Path(saida))

    def __enter__(self) -> "SessaoDeCifra":
        return self

    def __exit__(self, *_) -> None:
        self.sobra = limpeza.limpar(self.casa, self.casa.parent)


class Cifrador:
    """`with sessao.cifrador(arquivo) as c: c.write(bytes)...`: o gpg cifra para a chave pública e o texto cifrado vai para
    `arquivo` (NOVO, nunca sobrescreve), com SHA-256 e tamanho calculados enquanto grava (`c.sha256`, `c.tamanho`). Saída do
    bloco com erro, ou gpg com rc diferente de 0, apaga o arquivo e levanta CifraRecusada."""

    def __init__(self, sessao: SessaoDeCifra, saida: Path):
        self._s, self.saida = sessao, saida
        self._hash, self.tamanho, self.sha256 = hashlib.sha256(), 0, None
        self._erro = None
        self._stderr = b""

    def __enter__(self) -> "Cifrador":
        args = self._s.argumentos("--no-keyring", "--recipient-file", para_gpg(self._s.chave), "--trust-model", "always",
                                  "--cipher-algo", "AES256", "--compress-algo", "none", "--output", "-", "--encrypt")
        self._arq = open(self.saida, "xb")
        try:
            self._p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       env=_ambiente(), creationflags=_SEM_JANELA)
        except BaseException:
            self._arq.close()
            self.saida.unlink(missing_ok=True)
            raise
        self._fios = [threading.Thread(target=self._drenar, daemon=True), threading.Thread(target=self._ler_erros, daemon=True)]
        for fio in self._fios:
            fio.start()
        return self

    def _drenar(self) -> None:
        try:
            while bloco := self._p.stdout.read(_BLOCO):
                self._hash.update(bloco)
                self.tamanho += len(bloco)
                self._arq.write(bloco)
        except BaseException as exc:  # disco cheio e afins: derruba o gpg, senão o pipe de entrada travaria quem escreve
            self._erro = exc
            self._p.kill()

    def _ler_erros(self) -> None:
        self._stderr = self._p.stderr.read(4096)
        while self._p.stderr.read(_BLOCO):
            pass

    def write(self, dados) -> int:
        try:
            self._p.stdin.write(dados)
        except (OSError, ValueError) as exc:
            raise self._falha("o gpg parou antes do fim da escrita") from exc
        return len(dados)

    def _falha(self, motivo: str) -> CifraRecusada:
        self._encerrar()
        return CifraRecusada(motivo, codigo_gpg=self._p.returncode, saida_gpg=self._stderr.decode("utf-8", "replace")[:300],
                             erro_ao_gravar=type(self._erro).__name__ if self._erro else None)

    def _encerrar(self) -> None:
        try:
            self._p.stdin.close()
        except OSError:
            pass
        if self._p.poll() is None and self._erro is not None:
            self._p.kill()
        for fio in self._fios:
            fio.join()
        self._p.wait()
        self._p.stdout.close()
        self._p.stderr.close()
        self._arq.close()

    def __exit__(self, tipo, exc, _tb) -> None:
        if tipo is not None:
            if self._p.poll() is None:
                self._p.kill()
            self._encerrar()
            self.saida.unlink(missing_ok=True)
            return
        self._encerrar()
        if self._p.returncode != 0 or self._erro is not None:
            self.saida.unlink(missing_ok=True)
            raise self._falha("o gpg não terminou a cifra")
        self.sha256 = self._hash.hexdigest()


def _cabecalho(d: bytes, i: int) -> tuple[int, int, int | None]:
    """(tag, tamanho do cabeçalho, tamanho do corpo ou None se parcial ou até o fim) do pacote OpenPGP em d[i:]."""
    if i >= len(d) or not d[i] & 0x80:
        raise ValueError("não é um pacote OpenPGP")
    b = d[i]
    if b & 0x40:  # formato novo
        tag, resto = b & 0x3F, d[i + 1:i + 6]
        if not resto:
            raise ValueError("cabeçalho de pacote incompleto")
        o = resto[0]
        if o < 192:
            return tag, 2, o
        if o < 224:
            if len(resto) < 2:
                raise ValueError("cabeçalho de pacote incompleto")
            return tag, 3, ((o - 192) << 8) + resto[1] + 192
        if o < 255:
            return tag, 2, None  # comprimento parcial: o corpo segue até o fim da cifra
        if len(resto) < 5:
            raise ValueError("cabeçalho de pacote incompleto")
        return tag, 6, int.from_bytes(resto[1:5], "big")
    tag, tipo = (b >> 2) & 0xF, b & 3  # formato antigo
    n = (1, 2, 4, 0)[tipo]
    campo = d[i + 1:i + 1 + n]
    if len(campo) < n:
        raise ValueError("cabeçalho de pacote incompleto")
    return tag, 1 + n, int.from_bytes(campo, "big") if n else None


def conferir_cabecalho(prefixo: bytes, total: int, key_ids: set[str]) -> tuple[str, str] | None:
    """Os primeiros pacotes de uma parte, sem chamar o gpg: um ou mais PKESK v3 (tag 1) para as chaves de `key_ids`, e logo
    o dado cifrado (SEIPD, tag 18, ou AEAD, tag 20), sem pacote de chave, dado literal ou outro no topo. None se confere;
    senão (tipo, texto), com tipo "destinatario" ou "estrutura". Dado cifrado de tamanho definido tem de fechar com o
    tamanho do arquivo (`total`); o de tamanho parcial (o que o gpg grava por pipe) só se confere pelo hash e pelo MDC."""
    i, sessoes = 0, 0
    try:
        while True:
            tag, h, plen = _cabecalho(prefixo, i)
            if tag == 1:
                corpo = prefixo[i + h:i + h + (plen or 0)]
                if plen is None or len(corpo) < plen or plen < 10:
                    return "estrutura", "pacote de chave de sessão incompleto ou de tamanho não previsto"
                if corpo[0] != 3:
                    return "estrutura", f"pacote de chave de sessão de versão {corpo[0]} não prevista"
                if corpo[1:9].hex().upper() not in key_ids:
                    return "destinatario", "a parte foi cifrada para outra chave (ou para chave oculta)"
                sessoes, i = sessoes + 1, i + h + plen
            elif tag in (18, 20):
                if not sessoes:
                    return "estrutura", "dado cifrado sem pacote de chave de sessão"
                if plen is not None and i + h + plen != total:
                    return "estrutura", "o tamanho do dado cifrado não fecha com o do arquivo"
                return None
            else:
                return "estrutura", f"pacote inesperado no topo da parte (tag {tag})"
    except ValueError as exc:
        return "estrutura", str(exc)
