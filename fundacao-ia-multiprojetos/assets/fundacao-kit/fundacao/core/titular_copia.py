"""Lado do titular da cópia cifrada (1.7.11; desenho DESENHO-COPIA-CIFRADA-1.7.11, lote 4): o que a ferramenta fixa
(assets/host/fundacao_titular.py: preparar-chave-copia, conferir-copia, decifrar-copia) faz, no terminal dele, com a
chave privada e a senha. Mora no kit para entrar no hashes.json da cópia protegida, que a ferramenta confere antes de
importá-lo. Só biblioteca padrão mais o gpg de caminho fixo (cifra_copia.localizar_gpg).

- `preparar_chave`: cria o chaveiro dedicado (ed25519 de certificação + cv25519 de cifra; a senha é pedida na janela do
  pinentry do gpg, 3 vezes: criar, confirmar, exportar), grava a chave PÚBLICA para o `preparar-maquina.ps1 -ChaveDaCopia`
  instalar na âncora e a cópia da chave privada PROTEGIDA (pela senha) numa pasta à escolha, fora da raiz e do disco das cópias;
  o gpg-agent.conf do chaveiro tem o cache curto e o `s2k-count` máximo; o agente é encerrado no fim.
- `conferir_conteudo` (o conferir-copia mensal): âncora e partes sem senha primeiro; depois decifra cada parte em fluxo e
  confere o SHA-256 de cada arquivo contra o manifesto interno, sem gravar arquivo nenhum (o banco vai a uma pasta temporária
  privada para o `integrity_check` e sai); a decifra só vale com rc 0 do gpg. Grava {"conferida_em", "ok", ...} em
  conferencias-copia.jsonl (sem conteúdo), que o `backup situacao` lê como lembrete.
- `decifrar`: `decifra_copia.desembrulhar` para a pasta de uma cópia comum. A âncora é o `sha256_manifesto` que o titular
  digita (o do papel); o livro de cópias da raiz, que a sessão grava, só vale como segunda conferência, nunca sozinho
  (revisão de segurança da 1.7.11, F7). Sem o código: recusa, ou `aceitar_sem_ancora` (a escolha consciente dele).
- O chaveiro tem de caber nos ~85 caracteres na forma do msys (o soquete do agente do gpg do Git não nasce acima disso).
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import threading
from hashlib import sha256
from pathlib import Path

from . import backup, politica_cifra, preparo, publicacao
from .ancora_copia import _ancoras_do_livro, dentro_da_copia, ler_manifesto
from .backup_cifrado import MANIFESTO, _ler_externo, verificar_cifrada
from .cifra_copia import _BLOCO, _SEM_JANELA, CifraRecusada, SessaoDeCifra, _ambiente, localizar_gpg, para_gpg
from .contracts import FundacaoError, ValidationError
from .db import utcnow
from .decifra_copia import LIMITE_CASA, _nome_do_membro, desembrulhar, encerrar_agente

PRIVADA_PROTEGIDA = "chave-privada-protegida.asc"
CONF_AGENTE = "default-cache-ttl 60\nmax-cache-ttl 600\ns2k-count 65011712\n"  # cache curto e o máximo de iterações do S2K
TETO_MANIFESTO = 128 << 20


def chaveiro_padrao() -> Path:
    """%APPDATA%\\FundacaoIA\\gnupg-copia (no Linux, ~/.config/FundacaoIA/gnupg-copia)."""
    base = os.environ.get("APPDATA") if os.name == "nt" else None
    return Path(base) / "FundacaoIA" / "gnupg-copia" if base else Path.home() / ".config" / "FundacaoIA" / "gnupg-copia"


def publica_padrao() -> Path:
    return politica_cifra.pasta_de_dados() / "FundacaoIA" / "chave-da-copia.asc"


def conferir_chaveiro(casa) -> Path:
    """O chaveiro cabe no limite do soquete do agente (medido: ~85 caracteres na forma do msys); senão, CifraRecusada com o
    comprimento. Devolve o caminho absoluto."""
    casa = Path(os.path.abspath(casa))
    n = len(para_gpg(casa))
    if n > LIMITE_CASA:
        raise CifraRecusada(f"o chaveiro {casa} tem {n} caracteres na forma do gpg do Git (limite medido: ~{LIMITE_CASA}): o "
                            "agente do gpg não nasce acima disso; use um caminho mais curto (--casa)", caracteres=n,
                            limite=LIMITE_CASA)
    return casa


def _gpg(exe: str, casa: Path, extras: tuple, *args: str) -> subprocess.CompletedProcess:
    """O gpg no chaveiro, SEM --batch: a senha é pedida pelo pinentry. `extras` (só os testes): --batch e a senha por loopback."""
    return subprocess.run([exe, "--no-options", "--homedir", para_gpg(casa), *extras, *args], capture_output=True,
                          timeout=600, env=_ambiente(), creationflags=_SEM_JANELA)


def _impressoes(exe: str, casa: Path, extras: tuple) -> list[str]:
    r = _gpg(exe, casa, extras, "--with-colons", "--list-keys")
    return [x.split(":")[9] for x in r.stdout.decode("utf-8", "replace").splitlines() if x.startswith("fpr:")]


def preparar_chave(guardar_em, *, casa=None, publica=None, raiz=None, exe: str | None = None, extras_gpg: tuple = ()) -> dict:
    """Cria a chave da cópia (ver o módulo). `guardar_em`: pasta da cópia protegida da chave privada, fora da raiz."""
    casa, guardar = conferir_chaveiro(casa or chaveiro_padrao()), Path(os.path.abspath(guardar_em))
    publica = Path(os.path.abspath(publica or publica_padrao()))
    if raiz is not None and dentro_da_copia(guardar, raiz):
        raise CifraRecusada("a pasta da chave privada protegida fica dentro da raiz da fundação: use uma pasta fora dela")
    privada = guardar / PRIVADA_PROTEGIDA
    if privada.exists() or publica.exists() or (casa / "private-keys-v1.d").is_dir() and any((casa / "private-keys-v1.d").iterdir()):
        raise CifraRecusada("já existe chave da cópia neste chaveiro ou nos arquivos de saída: nada foi sobrescrito. Para outra "
                            "chave, use outro --casa e outros arquivos; para usar a que existe, instale a pública",
                            casa=str(casa), privada=str(privada), publica=str(publica))
    gpg = localizar_gpg(exe)["exe"]
    criado = not casa.exists()
    for pasta in (casa, guardar, publica.parent):
        pasta.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        casa.chmod(0o700)
    if not (casa / "gpg-agent.conf").exists():
        (casa / "gpg-agent.conf").write_text(CONF_AGENTE, encoding="utf-8", newline="\n")
    try:
        r = _gpg(gpg, casa, extras_gpg, "--quick-generate-key", "Copia da Fundacao IA", "ed25519", "cert", "never")
        if r.returncode != 0 or not (principal := (_impressoes(gpg, casa, extras_gpg) or [None])[0]):
            raise CifraRecusada("o gpg não criou a chave (senha não confirmada, janela cancelada ou chaveiro inválido)",
                                saida_gpg=r.stderr.decode("utf-8", "replace")[-300:])
        r = _gpg(gpg, casa, extras_gpg, "--quick-add-key", principal, "cv25519", "encr", "never")
        impressoes = _impressoes(gpg, casa, extras_gpg)
        if r.returncode != 0 or len(impressoes) < 2:
            raise CifraRecusada("o gpg não criou a subchave de cifra", saida_gpg=r.stderr.decode("utf-8", "replace")[-300:])
        for saida, comando in ((publica, "--export"), (privada, "--export-secret-keys")):
            r = _gpg(gpg, casa, extras_gpg, "--armor", "--output", para_gpg(saida), comando, principal)
            if r.returncode != 0 or not saida.is_file():
                raise CifraRecusada("o gpg não exportou a chave", arquivo=str(saida),
                                    saida_gpg=r.stderr.decode("utf-8", "replace")[-300:])
        with SessaoDeCifra(publica, gpg) as sessao:  # a pública serve ao kit, e é a mesma impressão
            if sessao.destinatario["principal"] != principal.upper():
                raise CifraRecusada("a chave pública exportada não é a criada")
    except BaseException:
        encerrar_agente(gpg, casa)
        if criado:
            shutil.rmtree(casa, ignore_errors=True)
        for resto in (publica, privada):
            resto.unlink(missing_ok=True)
        raise
    encerrar_agente(gpg, casa)
    return {"ok": True, "impressao_digital": principal.upper(), "subchave_de_cifra": impressoes[1].upper(),
            "chaveiro": str(casa), "chave_publica": str(publica), "chave_privada_protegida": str(privada),
            "proximos_passos": [
                "Escreva a impressão digital no papel da senha (a senha só existe na sua cabeça e no papel).",
                f"Copie {privada} para um terceiro lugar à parte (pen drive guardado fora, ou a sua nuvem). Sozinha, ela não "
                "abre nada sem a senha. Não a guarde no disco das cópias.",
                f"Instale a chave pública (pede o UAC): preparar-maquina.ps1 -ChaveDaCopia \"{publica}\" (com os mesmos "
                "-Raiz, -Titular, -Projeto e -Backups de sempre)."]}


def _registrar(registro: Path | None, linha: dict) -> None:
    arquivo = Path(registro or politica_cifra.pasta_de_dados() / "FundacaoIA" / politica_cifra.CONFERENCIAS)
    try:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        publicacao.anexar(arquivo, (json.dumps(linha, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    except (OSError, FundacaoError) as exc:
        linha["registro_nao_gravado"] = f"{type(exc).__name__}: o `backup situacao` continuará lembrando"


def _ler_parte(gpg: str, casa: Path, extras: tuple, caminho: Path, parte: dict, pasta: Path) -> tuple[dict, bytes | None, Path | None]:
    """Decifra `caminho` em fluxo e devolve ({membro: (sha256, tamanho)}, bytes do manifest.json, banco em `pasta`). Nada do claro
    é gravado, salvo o banco. A parte só vale com rc 0 e com a entrada igual ao manifesto externo; senão, CifraRecusada."""
    fd, _ = preparo._abrir(caminho, os.lstat(caminho))
    entrada, erros, membros, manifesto, banco = sha256(), [], {}, None, None
    contagem = {"lido": 0}
    p = subprocess.Popen([gpg, "--no-options", "--batch", "--no-tty", "--quiet", "--homedir", para_gpg(casa), *extras,
                          "--output", "-", "--decrypt"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, env=_ambiente(), creationflags=_SEM_JANELA)

    def alimentar() -> None:
        try:
            while bloco := os.read(fd, _BLOCO):
                entrada.update(bloco)
                contagem["lido"] += len(bloco)
                p.stdin.write(bloco)
        except OSError:
            pass
        finally:
            try:
                p.stdin.close()
            except OSError:
                pass

    fios = [threading.Thread(target=alimentar, daemon=True), threading.Thread(target=lambda: erros.append(p.stderr.read()), daemon=True)]
    for fio in fios:
        fio.start()
    problema = None
    try:
        with tarfile.open(fileobj=p.stdout, mode="r|") as tar:
            for membro in tar:
                partes = _nome_do_membro(membro.name)
                nome = "/".join(partes)
                if membro.isdir():
                    continue
                if not membro.isreg():
                    raise CifraRecusada("membro que não é arquivo nem pasta na parte decifrada", membro=membro.name[:200])
                resumo, tamanho, destino = sha256(), 0, None
                if nome == "state/state.sqlite":
                    banco = destino = open(pasta / "state.sqlite", "xb")
                corpo = bytearray() if nome == "manifest.json" else None
                with tar.extractfile(membro) as origem:
                    while bloco := origem.read(_BLOCO):
                        resumo.update(bloco)
                        tamanho += len(bloco)
                        if destino:
                            destino.write(bloco)
                        if corpo is not None:
                            corpo += bloco
                            if len(corpo) > TETO_MANIFESTO:
                                raise CifraRecusada("manifest.json decifrado grande demais")
                if destino:
                    destino.close()
                if nome in membros:
                    raise CifraRecusada("o mesmo membro duas vezes na parte decifrada", membro=nome)
                membros[nome] = (resumo.hexdigest(), tamanho)
                manifesto = bytes(corpo) if corpo is not None else manifesto
        while p.stdout.read(_BLOCO):
            pass
    except (CifraRecusada, tarfile.TarError, OSError) as exc:
        problema = exc
        p.kill()
    finally:
        for fio in fios:
            fio.join()
        codigo = p.wait()
        p.stdout.close()
        p.stderr.close()
        os.close(fd)
        if banco is not None and not banco.closed:
            banco.close()
    if problema is not None or codigo != 0 or contagem["lido"] != parte["tamanho"] or entrada.hexdigest() != parte["sha256"]:
        detalhe = f" ({type(problema).__name__}: {problema})" if problema is not None else ""
        raise CifraRecusada(f"a parte {parte['nome']} não decifrou, não confere ou mudou durante a leitura{detalhe}: o resultado "
                            "dela foi descartado", parte=parte["nome"], codigo_gpg=codigo,
                            saida_gpg=(erros[0] if erros else b"").decode("utf-8", "replace")[:300])
    return membros, manifesto, (pasta / "state.sqlite") if banco else None


def conferir_conteudo(origem, casa, *, sha256_manifesto: str | None = None, livro=None, destinatario_esperado: str | None = None,
                      exe: str | None = None, extras_gpg: tuple = (), registro=None, encerrar: bool = True) -> dict:
    """O conferir-copia (ver o módulo). Devolve {"ok", ...}; falha de conferência é ok False com o motivo (e fica no registro),
    não exceção. Chaveiro longo demais, gpg ausente e manifesto externo inválido continuam exceções (nada a registrar)."""
    origem, casa = Path(os.path.abspath(origem)), conferir_chaveiro(casa)
    bruto = preparo.ler(origem / MANIFESTO)
    ext = _ler_externo(bruto)
    linha = {"conferida_em": utcnow(), "ok": False, "rotulo": ext.get("label"), "partes": len(ext["partes"]),
             "impressao_digital": ext["destinatario"]["principal"]}
    sem_senha = verificar_cifrada(origem, sha256_manifesto=sha256_manifesto, livro=livro,
                                  destinatario_esperado=destinatario_esperado, bruto=bruto)
    linha["sha256_manifesto"] = sem_senha["ancora"]["sha256_manifesto"]
    if not sem_senha["ok"] or sem_senha["ancora"]["situacao"] == "divergente":
        linha["motivo"] = "as partes ou a âncora não conferem (conferência sem senha); o gpg não foi chamado"
        _registrar(registro, linha)
        return {**linha, "verificacao": sem_senha}
    gpg = localizar_gpg(exe)["exe"]
    pasta = Path(tempfile.mkdtemp(prefix="fundacao-conferencia-"))
    try:
        calculados, interno, banco = {}, None, None
        for parte in ext["partes"]:
            membros, manifesto, caminho_banco = _ler_parte(gpg, casa, tuple(extras_gpg), origem / parte["nome"], parte, pasta)
            if set(membros) & set(calculados):
                raise CifraRecusada("membro repetido entre partes", parte=parte["nome"])
            calculados.update(membros)
            interno, banco = manifesto or interno, caminho_banco or banco
        if interno is None or sha256(interno).hexdigest() != ext["sha256_manifesto_interno"]:
            raise CifraRecusada("o manifest.json decifrado não é o ancorado no manifesto externo")
        manifest = ler_manifesto(interno)
        esperados = {f"files/{f['path']}": f["sha256"] for f in manifest["files"]}
        if manifest.get("db_sha256"):
            esperados["state/state.sqlite"] = manifest["db_sha256"]
        calculados.pop("manifest.json", None)
        diferentes = sorted(n for n in set(esperados) | set(calculados) if esperados.get(n) != (calculados.get(n) or (None,))[0])
        if diferentes:
            raise CifraRecusada(f"{len(diferentes)} arquivo(s) decifrado(s) não conferem com o manifesto interno (ausentes, "
                                "a mais ou trocados)", exemplos=diferentes[:3])
        if banco is not None:
            try:
                integro = backup.logical_summary(banco, copia=True)["integrity_check"] == "ok"
            except sqlite3.Error:
                integro = False
            if not integro:
                raise CifraRecusada("o banco decifrado não passou no integrity_check")
        linha.update(ok=True, arquivos=len(manifest["files"]), banco="íntegro" if banco is not None else "ausente na cópia")
    except (CifraRecusada, FundacaoError, OSError) as exc:
        linha["motivo"] = str(exc)[:400]
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
        if encerrar:
            encerrar_agente(gpg, casa)
    _registrar(registro, linha)
    return linha


def exigir_ancora_do_titular(sha256_manifesto, aceitar_sem_ancora: bool = False) -> str | None:
    """A âncora do `decifrar-copia` vem do titular: o `sha256_manifesto` que ele guardou FORA do computador. O livro
    `state/copias.jsonl` não basta, porque uma sessão grava nele (R177-KIT-01; revisão da 1.7.11, F7). Devolve o código
    limpo, ou None só com `aceitar_sem_ancora` (a escolha consciente dele); senão, ValidationError com o que fazer."""
    codigo = sha256_manifesto.strip() if isinstance(sha256_manifesto, str) else ""
    if codigo:
        return codigo
    if aceitar_sem_ancora:
        return None
    raise ValidationError("o decifrar-copia exige a âncora que você guardou fora do computador: informe --sha256-manifesto "
                          "<o código que o `backup criar` devolveu, anotado no papel ou no gerenciador de senhas>. O livro "
                          "state/copias.jsonl não basta, porque a sessão grava nele. Se perdeu o código e quer decifrar mesmo "
                          "assim, repita o comando com --aceitar-sem-ancora (decifra uma cópia que nada fora da pasta confirma)")


def decifrar(origem, destino, casa, *, sha256_manifesto: str | None = None, livro=None, aceitar_sem_ancora: bool = False,
             **kw) -> dict:
    """O decifrar-copia: `desembrulhar` com o chaveiro conferido (ver decifra_copia). A âncora é a do titular; sem ela, só
    com `aceitar_sem_ancora`, e então o livro nem entra (não ancora sozinho). Com ela, o livro é só uma segunda conferência
    (`livro_de_copias`: consta, nao_consta ou ausente), que avisa e não decide."""
    casa = conferir_chaveiro(casa)
    codigo = exigir_ancora_do_titular(sha256_manifesto, aceitar_sem_ancora)
    r = desembrulhar(origem, destino, casa, sha256_manifesto=codigo, livro=None, aceitar_sem_ancora=aceitar_sem_ancora, **kw)
    if codigo is None:
        return r
    anotadas = _ancoras_do_livro(Path(livro)) if livro is not None and not dentro_da_copia(livro, origem) else None
    r["livro_de_copias"] = "ausente" if anotadas is None else "consta" if r["ancora"]["sha256_manifesto"] in anotadas else "nao_consta"
    if r["livro_de_copias"] == "nao_consta":
        r["aviso_livro"] = ("a cópia conferiu pelo seu código, mas não consta no livro state/copias.jsonl: confira se o código "
                            "é o desta cópia e, na dúvida, trate o livro como não confiável")
    return r
