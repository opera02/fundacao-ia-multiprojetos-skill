"""Apoio aos testes da cópia cifrada (1.7.11): chaves de TESTE criadas aqui, numa pasta temporária curta (o soquete do
agente do gpg de msys não nasce com --homedir acima de ~85 caracteres), apagadas no fim com o agente encerrado; cópia
sintética em claro; decifra de uma parte com a chave de teste. Nenhuma chave real, nenhum dado real. Sem `gpg` no ambiente,
quem usa pula com o motivo (`exigir_gpg`)."""

from __future__ import annotations

import atexit
import hashlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from helpers import KIT  # noqa: F401 — põe o kit no sys.path antes do import abaixo

from fundacao.core import cifra_copia
from fundacao.core.canon import sha256_bytes

# Valor de teste montado por partes: a varredura de segredos do pacote não toma por segredo atribuído.
FRASE_DE_TESTE = "-".join(("frase", "de", "teste", "ficticia"))
DOMINIO_DE_TESTE = "example" + ".invalid"
LOOPBACK = ("--pinentry-mode", "loopback", "--passphrase", FRASE_DE_TESTE)  # só nos testes: o titular digita a senha na janela do gpg
CANARIO = "CANARIO-0f3a9c1e-FICTICIO"


def exigir_gpg() -> str:
    try:
        return cifra_copia.localizar_gpg()["exe"]
    except cifra_copia.CifraRecusada as exc:
        raise unittest.SkipTest(f"sem gpg 2.4 no caminho fixo: {exc}") from None


def _gpg(exe: str, casa: Path, *args: str, entrada: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([exe, "--no-options", "--batch", "--no-tty", "--homedir", cifra_copia.para_gpg(casa), *args],
                          input=entrada, capture_output=True, timeout=120, env=cifra_copia._ambiente())


class Chaveiro:
    """Um chaveiro de teste com uma chave (ed25519 + cv25519 de cifra) protegida por FRASE_DE_TESTE."""

    def __init__(self, exe: str, nome: str = "Teste"):
        self.exe = exe
        self.casa = Path(tempfile.mkdtemp(prefix="gt"))
        if len(cifra_copia.para_gpg(self.casa)) > 80:
            raise unittest.SkipTest("pasta temporária longa demais para o agente do gpg (limite medido: ~85 caracteres)")
        base = ("--pinentry-mode", "loopback", "--passphrase", FRASE_DE_TESTE)
        r = _gpg(exe, self.casa, *base, "--quick-generate-key", f"{nome} <teste@{DOMINIO_DE_TESTE}>", "ed25519", "cert", "never")
        assert r.returncode == 0, r.stderr
        listagem = _gpg(exe, self.casa, "--with-colons", "--list-keys").stdout.decode()
        self.impressao = next(x.split(":")[9] for x in listagem.splitlines() if x.startswith("fpr:"))
        r = _gpg(exe, self.casa, *base, "--quick-add-key", self.impressao, "cv25519", "encr", "never")
        assert r.returncode == 0, r.stderr
        fprs = [x.split(":")[9] for x in _gpg(exe, self.casa, "--with-colons", "--list-keys").stdout.decode().splitlines()
                if x.startswith("fpr:")]
        self.subchave = fprs[1]
        self.publica = self.casa / "publica.asc"
        _gpg(exe, self.casa, "--armor", "--output", cifra_copia.para_gpg(self.publica), "--export", self.impressao)
        self.privada = self.casa / "privada.asc"
        _gpg(exe, self.casa, *base, "--armor", "--output", cifra_copia.para_gpg(self.privada), "--export-secret-keys",
             self.impressao)

    def decifrar(self, parte: Path) -> tuple[int, bytes]:
        """(código do gpg, texto claro que ele entregou) — o claro só vale com código 0."""
        r = _gpg(self.exe, self.casa, "--pinentry-mode", "loopback", "--passphrase", FRASE_DE_TESTE, "--output", "-", "--decrypt",
                 cifra_copia.para_gpg(parte))
        return r.returncode, r.stdout

    def extrair(self, pasta_cifrada: Path, destino: Path) -> list[str]:
        """Decifra as partes na ordem do manifesto e extrai os tars em `destino`; devolve os membros de cada parte."""
        manifesto = json.loads((pasta_cifrada / "manifesto-cifrado.json").read_text(encoding="utf-8"))
        destino.mkdir(exist_ok=True)
        membros = []
        for parte in manifesto["partes"]:
            codigo, claro = self.decifrar(pasta_cifrada / parte["nome"])
            assert codigo == 0, f"não decifrou {parte['nome']}"
            with tarfile.open(fileobj=io.BytesIO(claro), mode="r:") as tar:
                membros.append([m.name for m in tar.getmembers()])
                tar.extractall(destino, filter="data")
        return membros

    def encerrar_agente(self) -> None:
        """Encerra o gpg-agent deste chaveiro (a chave desbloqueada não fica na memória); ele sobe de novo se precisar."""
        subprocess.run([str(Path(self.exe).with_name("gpgconf.exe") if os.name == "nt" else "gpgconf"), "--homedir",
                        cifra_copia.para_gpg(self.casa), "--kill", "gpg-agent"], capture_output=True, timeout=60,
                       env=cifra_copia._ambiente())

    def apagar(self) -> None:
        subprocess.run([str(Path(self.exe).with_name("gpgconf.exe") if os.name == "nt" else "gpgconf"), "--homedir",
                        cifra_copia.para_gpg(self.casa), "--kill", "all"], capture_output=True, timeout=60,
                       env=cifra_copia._ambiente())
        for _ in range(20):  # o agente solta a pasta um instante depois de encerrar
            shutil.rmtree(self.casa, ignore_errors=True)
            if not self.casa.exists():
                return
            time.sleep(0.25)


_CHAVEIROS: dict = {}


def chaveiros(*nomes: str) -> list[Chaveiro]:
    """Chaveiros de teste pelo nome, criados UMA vez por processo (os que faltam, em paralelo) e apagados na saída do
    processo: os módulos de teste da cópia cifrada, que rodam juntos no ensaio do atualizador, dividem as chaves em vez de
    gerar duas por módulo. Nenhum teste altera a chave; o agente é encerrado pelo teste que depende de senha pedida."""
    exe = exigir_gpg()
    faltam = [n for n in nomes if n not in _CHAVEIROS]
    if faltam:
        with ThreadPoolExecutor(len(faltam)) as pool:
            for nome, chaveiro in zip(faltam, pool.map(lambda n: Chaveiro(exe, n), faltam)):
                _CHAVEIROS[nome] = chaveiro
    unittest.addModuleCleanup(encerrar_agentes)  # ao fim de CADA módulo: nenhum gpg-agent fica vivo entre eles
    return [_CHAVEIROS[n] for n in nomes]


def encerrar_agentes() -> None:
    for chaveiro in _CHAVEIROS.values():
        chaveiro.encerrar_agente()


@atexit.register
def _apagar_chaveiros() -> None:
    for chaveiro in _CHAVEIROS.values():
        chaveiro.apagar()


def sha(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def copia_sintetica(pasta: Path, arquivos: dict[str, bytes], com_banco: bool = True, vazias=("files/projects/vazio",)) -> dict:
    """Monta em `pasta` uma cópia no formato do `backup criar` (manifest.json, files/, state/state.sqlite) com `arquivos`
    (caminho relativo -> bytes). Devolve o manifesto."""
    pasta.mkdir(parents=True)
    lista = []
    for rel, dados in sorted(arquivos.items()):
        alvo = pasta / "files" / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(dados)
        lista.append({"path": rel, "size": len(dados), "sha256": sha(dados)})
    for rel in vazias:
        (pasta / rel).mkdir(parents=True, exist_ok=True)
    manifesto = {"schema_version": "fundacao.backup/1", "label": "teste-cifrado", "created_at": "2026-11-08T12:00:00.000000Z",
                 "db": None, "db_sha256": None, "files": lista, "retiradas": None}
    if com_banco:
        (pasta / "state").mkdir()
        con = sqlite3.connect(pasta / "state" / "state.sqlite")
        con.execute("create table t (a text)")
        con.execute("insert into t values (?)", (CANARIO,))
        con.commit()
        con.close()
        manifesto["db_sha256"] = sha((pasta / "state" / "state.sqlite").read_bytes())
    (pasta / "manifest.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifesto


def arquivos_de_teste() -> dict[str, bytes]:
    """Conteúdos fictícios: um canário no nome e no conteúdo, e arquivos grandes o bastante para dar várias partes."""
    return {
        f"projects/{CANARIO}/caso.txt": f"conteudo secreto {CANARIO}\n".encode(),
        "projects/p1/a.bin": os.urandom(30_000),
        "projects/p1/b.bin": os.urandom(30_000),
        "projects/p1/dados/c.bin": os.urandom(30_000),
        "projects/p2/grande.bin": os.urandom(90_000),  # acima do limite de parte usado nos testes: fica numa parte só
        "AGENTS.md": "instruções fictícias\n".encode(),
    }


def tar_da_copia(claro: Path, extras=(), sem=()) -> bytes:
    """Um tar como o do kit com a cópia em `claro` (manifest.json, state/, files/), mais os `extras` forjados (nome, tipo,
    dados, destino da ligação); `sem`: nomes que ficam de fora."""
    saida = io.BytesIO()
    with tarfile.open(fileobj=saida, mode="w:", format=tarfile.PAX_FORMAT) as tar:
        for caminho in sorted(p for p in claro.rglob("*") if p.is_file()):
            nome = caminho.relative_to(claro).as_posix()
            if nome not in sem:
                info = tarfile.TarInfo(nome)
                info.size = caminho.stat().st_size
                tar.addfile(info, io.BytesIO(caminho.read_bytes()))
        for nome, tipo, dados, alvo in extras:
            info = tarfile.TarInfo(nome)
            info.type, info.size, info.linkname = tipo, len(dados), alvo
            tar.addfile(info, io.BytesIO(dados))
    return saida.getvalue()


def cifrada_de_um_tar(pasta: Path, claro: Path, tar_bytes: bytes, chave: "Chaveiro", exe: str) -> str:
    """Uma cópia cifrada de uma parte só (a final) com o `tar_bytes` dado, para a chave de teste, com o manifesto externo
    consistente (hashes certos): o forjador que passou pela âncora. Devolve o SHA-256 do manifesto externo."""
    pasta.mkdir()
    with cifra_copia.SessaoDeCifra(chave.publica, exe) as sessao:
        with sessao.cifrador(pasta / "parte-final.gpg") as cifrador:
            cifrador.write(tar_bytes)
    parte = pasta / "parte-final.gpg"
    externo = {"schema_version": "fundacao.backup_cifrado/1", "label": "forjada", "created_at": "2026-11-08T12:00:00.000000Z",
               "kit_version": "x", "gpg_versao": "2.4.9", "formato": "tar-pax+openpgp-seipd",
               "destinatario": {"principal": chave.impressao, "subchaves_de_cifra": [chave.subchave]},
               "sha256_manifesto_interno": sha((claro / "manifest.json").read_bytes()), "arquivos": 0, "bytes": 0,
               "tamanho_parte": 65536, "partes": [{"nome": parte.name, "tamanho": parte.stat().st_size,
                                                   "sha256": sha(parte.read_bytes()), "membros": 1}]}
    bruto = json.dumps(externo, indent=2).encode("utf-8")
    (pasta / "manifesto-cifrado.json").write_bytes(bruto)
    return sha256_bytes(bruto)


def conteudo_da_pasta(pasta: Path) -> dict[str, bytes]:
    return {p.relative_to(pasta).as_posix(): p.read_bytes() for p in sorted(pasta.rglob("*")) if p.is_file()}
