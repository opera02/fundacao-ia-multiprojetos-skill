"""Decifra de uma cópia cifrada de volta para a pasta de cópia comum (1.7.11; desenho DESENHO-COPIA-CIFRADA-1.7.11, lote 2;
medida MEDIDA-GPG-20261108). Quem chama é a ferramenta do titular (decifrar-copia), no terminal dele: a chave privada e a
senha (na janela do pinentry do gpg) ficam no chaveiro `casa`; nada disto roda dentro de uma sessão.

Ordem, sempre: (1) `verificar_cifrada` — âncora, tamanho e SHA-256 de cada parte e destinatário — ANTES de chamar o gpg: cópia
alterada recusa sem pedir a senha; cópia sem âncora conferida só com `aceitar_sem_ancora`. (2) Cada parte entra no gpg lida
do objeto listado (sem seguir ligação), com o SHA-256 recalculado no caminho, e o claro do gpg vai para um arquivo temporário:
o gpg entrega o claro ANTES de conferir o MDC (rc 2 no fim), então a parte só é aceita com rc 0 E o hash da entrada igual ao
do manifesto; na falha o claro sai e a decifra inteira é descartada. (3) O tar aceito é extraído por um extrator seguro: só
arquivo comum e pasta, nome relativo sem `..`, `:` ou `\\`, só `manifest.json`, `state/state.sqlite` e `files/...`, criação
exclusiva (nada é sobrescrito nem escrito através de ligação). (4) Com todas as partes, o manifest.json tem de ter o SHA-256
`sha256_manifesto_interno` do manifesto externo e a pasta passa pelo `verify_backup` de hoje contra ele (arquivo a mais ou
fora do manifesto não confere). Só então a pasta é promovida. O agente do gpg é encerrado no fim: a chave aberta não fica na
memória. A pasta decifrada é dado em claro: quem a apaga depois da restauração é o titular.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tarfile
import threading
from pathlib import Path

from . import backup, limpeza, preparo
from .ancora_copia import _caminho_valido
from .backup_cifrado import MANIFESTO, _ler_externo, verificar_cifrada
from .cifra_copia import _BLOCO, _SEM_JANELA, CifraRecusada, _ambiente, localizar_gpg, para_gpg
from .contracts import ValidationError

LIMITE_CASA = 85  # caracteres do --homedir na forma de msys; acima disso o soquete do agente não nasce (medido)


def encerrar_agente(exe: str, casa) -> None:
    """`gpgconf --kill gpg-agent` no chaveiro: a chave desbloqueada não fica na memória para outras sessões."""
    gpgconf = Path(exe).with_name("gpgconf.exe" if os.name == "nt" else "gpgconf")
    try:
        subprocess.run([str(gpgconf), "--homedir", para_gpg(casa), "--kill", "gpg-agent"], capture_output=True, timeout=30,
                       env=_ambiente(), creationflags=_SEM_JANELA)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _decifrar_parte(exe: str, casa: Path, extras: tuple, caminho: Path, parte: dict, saida: Path) -> None:
    """Decifra `caminho` para o arquivo novo `saida`; só fica se o gpg sair com 0 e a entrada tiver o hash e o tamanho do
    manifesto. Senão `saida` é apagado e CifraRecusada diz que a parte inteira foi descartada."""
    fd, _ = preparo._abrir(caminho, os.lstat(caminho))
    sha, lido, erros = hashlib.sha256(), 0, []
    args = [exe, "--no-options", "--batch", "--no-tty", "--quiet", "--homedir", para_gpg(casa), *extras,
            "--output", "-", "--decrypt"]
    try:
        with open(saida, "xb") as claro:
            p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=claro, stderr=subprocess.PIPE, env=_ambiente(),
                                 creationflags=_SEM_JANELA)
            fio = threading.Thread(target=lambda: erros.append(p.stderr.read()), daemon=True)
            fio.start()
            try:
                while bloco := os.read(fd, _BLOCO):
                    sha.update(bloco)
                    lido += len(bloco)
                    p.stdin.write(bloco)
            except OSError:  # o gpg encerrou antes do fim (senha errada, parte inválida): o código de saída diz
                pass
            finally:
                try:
                    p.stdin.close()
                except OSError:
                    pass
            codigo = p.wait()
            fio.join()
            p.stderr.close()
    finally:
        os.close(fd)
    if codigo != 0 or lido != parte["tamanho"] or sha.hexdigest() != parte["sha256"]:
        saida.unlink(missing_ok=True)
        raise CifraRecusada(f"a parte {parte['nome']} não decifrou ou mudou durante a leitura: a parte inteira foi "
                            "descartada e nada foi liberado", parte=parte["nome"], codigo_gpg=codigo,
                            entrada_confere=lido == parte["tamanho"] and sha.hexdigest() == parte["sha256"],
                            saida_gpg=(erros[0] if erros else b"").decode("utf-8", "replace")[:300])


def _nome_do_membro(nome: str) -> tuple[str, ...]:
    """Partes do caminho de um membro do tar, ou CifraRecusada: só `manifest.json`, `state`, `state/state.sqlite`, `files` e
    `files/<caminho válido>`; nada de caminho absoluto, `..`, `\\`, `:` ou NUL."""
    limpo = nome.rstrip("/")
    ok = (limpo in ("manifest.json", "state", "state/state.sqlite", "files")
          or (limpo.startswith("files/") and _caminho_valido(limpo[len("files/"):])))
    if not ok or any(c in limpo for c in "\\:\0") or limpo.startswith("/"):
        raise CifraRecusada("a cópia decifrada traz um membro fora do formato (caminho absoluto, '..', fora de files/ e "
                            "state/): recusada", membro=nome[:200])
    return tuple(limpo.split("/"))


def _extrair(tar_arquivo: Path, base: Path, criadas: set) -> int:
    """Extrai o tar para `base` (pasta de preparo) pelas regras do módulo; devolve quantos arquivos comuns."""
    arquivos = 0
    with tarfile.open(tar_arquivo, "r:") as tar:
        for membro in tar:
            alvo = base.joinpath(*_nome_do_membro(membro.name))
            if membro.isdir():
                preparo.criar_pasta(alvo, criadas)
            elif membro.isreg():
                preparo.criar_pasta(alvo.parent, criadas)
                try:
                    with tar.extractfile(membro) as origem, open(alvo, "xb") as destino:
                        shutil.copyfileobj(origem, destino, _BLOCO)
                except FileExistsError:
                    raise CifraRecusada("a cópia decifrada traz o mesmo membro duas vezes: recusada",
                                        membro=membro.name[:200]) from None
                os.utime(alvo, (membro.mtime, membro.mtime))
                arquivos += 1
            else:
                raise CifraRecusada("a cópia decifrada traz membro que não é arquivo nem pasta (ligação, dispositivo...): "
                                    "recusada", membro=membro.name[:200], tipo=membro.type.decode("latin-1"))
    return arquivos


def desembrulhar(origem, destino, casa, *, sha256_manifesto: str | None = None, livro: Path | None = None,
                 destinatario_esperado: str | None = None, aceitar_sem_ancora: bool = False, exe: str | None = None,
                 extras_gpg: tuple = (), encerrar: bool = True) -> dict:
    """Decifra a cópia cifrada `origem` para a pasta nova `destino` (a pasta de uma cópia comum), com a chave de `casa`.
    `extras_gpg`: opções do gpg a mais (os testes passam `--pinentry-mode loopback --passphrase ...`; o titular não passa
    nada: a senha vai na janela do pinentry). Devolve o resumo; qualquer falha deixa o destino ausente."""
    origem, destino, casa = Path(os.path.abspath(origem)), Path(os.path.abspath(destino)), Path(os.path.abspath(casa))
    if destino.exists() and any(destino.iterdir()):
        raise FileExistsError("destino da decifra não vazio: use uma pasta nova")
    ligada = preparo.ligacao_no_caminho(destino) or preparo.ligacao_no_caminho(origem) or preparo.ligacao_no_caminho(casa)
    if ligada:
        raise ValidationError("a origem, o destino ou o chaveiro passa por ligação: informe o caminho real", caminho=ligada)
    if backup.dentro_da_copia(destino, origem):
        raise ValidationError("o destino da decifra fica dentro da cópia cifrada", destino=str(destino))
    bruto = preparo.ler(origem / MANIFESTO)  # os bytes que valem daqui em diante
    ext = _ler_externo(bruto)
    v = verificar_cifrada(origem, sha256_manifesto=sha256_manifesto, livro=livro, destinatario_esperado=destinatario_esperado,
                          bruto=bruto)
    if not v["ok"]:
        raise ValidationError("a cópia cifrada não confere (veja a verificação): o gpg não foi chamado e a senha não foi pedida",
                              verificacao=v)
    if v["ancora"]["situacao"] != "conferida" and not aceitar_sem_ancora:
        raise ValidationError("a cópia cifrada não tem âncora conferida (sha256_manifesto guardado fora ou livro): o gpg não "
                              "foi chamado; informe a âncora ou aceite a decifra sem ela de caso pensado", verificacao=v)
    if len(para_gpg(casa)) > LIMITE_CASA:
        raise CifraRecusada(f"o chaveiro tem caminho de {len(para_gpg(casa))} caracteres (limite medido: ~{LIMITE_CASA}): o "
                            "agente do gpg não nasce; use um chaveiro em caminho mais curto", casa=str(casa))
    gpg = localizar_gpg(exe)
    interno = ext["sha256_manifesto_interno"]
    pasta = preparo.criar_preparo(destino)
    temp = preparo.criar_preparo(destino.with_name(destino.name + "-parte"))
    try:
        with limpeza.contada(temp, temp.parent), limpeza.contada(pasta, destino.parent) as sobra:
            criadas, arquivos = {pasta}, 0
            for parte in ext["partes"]:
                tar_arquivo = temp / "parte.tar"
                _decifrar_parte(gpg["exe"], casa, tuple(extras_gpg), origem / parte["nome"], parte, tar_arquivo)
                arquivos += _extrair(tar_arquivo, pasta, criadas)
                tar_arquivo.unlink()
            if not os.path.lexists(pasta / "manifest.json") or preparo.resumo(
                    pasta / "manifest.json", os.lstat(pasta / "manifest.json")) != interno:
                raise ValidationError("o manifest.json decifrado não é o ancorado no manifesto externo: nada foi liberado")
            conferencia = backup.verify_backup(pasta, sha256_manifesto=interno)
            if not conferencia["ok"]:
                raise ValidationError("a pasta decifrada não confere com o manifesto interno (arquivo a mais, trocado ou "
                                      "ausente): nada foi liberado", conferencia=conferencia)
            preparo.promover(pasta, destino)
    finally:
        if encerrar:
            encerrar_agente(gpg["exe"], casa)
    return {"ok": True, "destino": str(destino), "partes": len(ext["partes"]), "arquivos": arquivos,
            "sha256_manifesto_interno": interno, "conteudo_conferido": True, "ancora": v["ancora"],
            **({"aviso_ancora": v["aviso_ancora"]} if v.get("aviso_ancora") else {}), **limpeza.no_resultado(sobra),
            "proximo_passo": ("restaure como uma cópia comum: backup restaurar --origem <destino> --destino <pasta nova> "
                              "--retiradas <registro> --sha256-manifesto <sha256_manifesto_interno>")}
