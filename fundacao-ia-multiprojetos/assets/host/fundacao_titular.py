#!/usr/bin/env python3
"""Ferramenta fixa do titular para a ficha de aberturas do projeto (1.7.10; contratos do lote 2, §5; crítica do
desenho: "toda cerimônia do titular passa por um utilitário fixo que mostra o conteúdo por código confiável").

  <python fixado> -I -B -S <cópia protegida>/assets/host/fundacao_titular.py assinar-ficha --raiz R --projeto P
      [--versao N] [--chave ARQ]
  <python fixado> -I -B -S <cópia protegida>/assets/host/fundacao_titular.py verificar-ficha --raiz R --projeto P
      [--versao N]

(-S: nenhum .pth de site-packages roda antes da ferramenta, que só usa a biblioteca padrão; -I não implica -S. Item I13
da integração e revisão da integração, defeito 8.)

Roda fora do Claude, de preferência pela caixa Executar (Win+R), que abre o Python fixado direto, sem o perfil de um
shell ($PROFILE, ~/.bashrc), que a sessão pode ter gravado: um terminal novo também o carrega (a forma pronta vem de
core/aberturas_comando.comando_do_titular); no Windows, também pelo `preparar-projeto.ps1 -AssinarFicha`. Com terminal,
espera um Enter no fim, depois do resultado: a janela da caixa Executar fecharia com ele (reconferência do pacote,
01/11/2026). Recebe só raiz, projeto, versão e o caminho da chave dele: o que a ficha abre vem do arquivo, conferido
aqui, nunca de um comando montado pela sessão. Só biblioteca padrão.

Cópia protegida (revisão independente do pacote ABERTURAS, 31/10/2026): a ferramenta só é confiável numa pasta que
nenhuma sessão grava — no Windows, `C:\\ProgramData\\FundacaoIA\\ferramentas\\<versão>\\` (ACL de administrador,
instalada pelo preparo do titular com UAC), chamada pelo Python fixado pelo caminho completo; no Ubuntu,
`/usr/local/lib/fundacao-ia/<versão>/` (root:root, 0755), por `/usr/bin/python3`. Ali, ANTES de importar o kit e de
mostrar qualquer coisa, ela confere o SHA-256 dela e de cada arquivo de `assets/fundacao-kit/fundacao/**` contra o
`hashes.json` da cópia (`fundacao.ferramenta_titular/1`, como o lançador faz com o porteiro.py), o dono e os direitos
(root sem escrita de grupo nem de outros; no Windows, esta conta não altera arquivo nem pasta da cópia), o Python que
roda (no Windows, o registrado no hashes.json) e, antes de assinar, que a âncora está protegida (no POSIX por
decisoes.conferir_ancora; no Windows por sondas em processo, SEM powershell.exe nem icacls, que rodariam pelo nome nu
no meio da cerimônia); qualquer diferença recusa. Quem instala as cópias (folha da integração, I11; I24): no Ubuntu, o
preparo do projeto (`preparar-wsl.sh`, pelo `preparo_host.py instalar-projeto` com sudo) grava a cópia em
`/usr/local/lib/fundacao-ia/<versão do kit>/`; no Windows, o `preparar-maquina.ps1` grava a dele no mesmo UAC da
âncora, só com um Python instalado para todos os usuários (o que o hashes.json registra). Com o Python por usuário (em
AppData), a forma do Windows fica pendente, com o motivo no relatório do preparo, e vale a do Ubuntu (`executar_ubuntu`,
pelo wsl.exe). LIMITE que fica: fora da cópia protegida (a cópia da skill, no perfil do usuário, que o
`preparar-projeto.ps1 -AssinarFicha` chama quando a protegida não confere), a ferramenta pode ser alterada por qualquer
sessão do Windows (sem sandbox) e pelos comandos de uma sessão com a raiz em /mnt/e (contratos, §0), e uma cópia
alterada pode mostrar uma ficha e assinar outra, ou pedir a senha por conta própria. Fora da cópia protegida, a
ferramenta diz isso na tela, antes da pergunta; o comando fixo do kit (core/aberturas.comando_do_titular) só aponta
para a cópia protegida.

`assinar-ficha`:
1. usa o kit DESTA cópia (assets/fundacao-kit, ao lado) e recusa se o validador do kit da raiz
   (`<raiz>/fundacao/core/aberturas*.py`, com o `manutencao.py` das listas de segredo e o `contracts.py`: VALIDADOR)
   não for idêntico byte a byte ao dela: valida com o mesmo validador que a raiz usa, sem executar código da raiz;
2. lê sem seguir ligação (no POSIX, pela pasta aberta) a ficha preparada `projects/<p>/outputs/aberturas/
   ficha-v<N>.json` (a maior, sem `--versao`) e confere tudo de novo: tetos fixos, projeto, versão (maior que a já
   assinada na caixa de entrada e, no Linux, que a já instalada na área do titular), vigência e cada plugin no disco;
3. antes de pedir a senha, confere que a âncora aceita a chave no namespace `fundacao-abertura` (a linha da 1.7.9 só
   aceita `fundacao-decisao`: a recusa diz como atualizar);
4. mostra PRIMEIRO o texto da sessão (motivo e consequências), em faixas de até 70 colunas (até 12 por campo) marcadas
   com '    | ', e DEPOIS, até a pergunta, só texto fixo: o que abre, o que muda em relação à ficha já
   assinada, a validade, os avisos e o "Importante" (nada da sessão fica entre a lista verdadeira e a pergunta);
5. exige que o titular digite o nome do projeto; sem terminal interativo, recusa;
6. assina os bytes canônicos com o `ssh-keygen -Y sign -n fundacao-abertura` do sistema e a chave do titular (a senha
   é pedida pelo próprio ssh-keygen; o ssh-agent fica fora, e o ambiente dele é o mínimo, sem SSH_SK_PROVIDER,
   SSH_SK_HELPER nem SSH_ASKPASS que uma sessão tenha plantado), confere a assinatura contra a âncora e grava a ficha
   e o `.sig` na caixa de entrada `<raiz>/.claude/projetos/<p>/ficha/`, sem seguir ligação e sem sobrescrever outra
   versão. No Ubuntu, o preparo do projeto (sudo) a instala depois na área do titular, de dono root.
`verificar-ficha`: a ficha em vigor na caixa de entrada e, no Linux, na área do titular (ou a da `--versao`), em JSON.

Códigos: 0 assinada (ou já assinada, igual), ou vale a ficha que conta neste sistema (no Linux, a instalada na área do
titular; no Windows, a da caixa de entrada); 1 o titular não confirmou (nada gravado); 2 recusada (nada gravado); 3 a
ficha que conta não vale (verificar-ficha).

Honestidade (contratos do lote 2, §0): a assinatura não basta. Com a raiz em /mnt/e, o isolamento entre projetos no
Ubuntu é lógico até o canário passar; a ficha só vale com o resultado do canário no checklist do projeto.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import traceback
import unicodedata
from datetime import date
from pathlib import Path
from types import SimpleNamespace

AQUI = Path(__file__).resolve().parent
KIT = AQUI.parent / "fundacao-kit"
# O validador da ficha e dos plugins, conferido idêntico ao do kit da raiz (integração, rodada 2, item I16: as regras de
# cada Markdown saíram do aberturas_plugins.py para o aberturas_markdown.py, que entra aqui com ele). Também os módulos
# de que a regra depende (revisão da integração, rodada 2): o manutencao.py, de onde saem as listas de nome forte e de
# pasta de segredo (NOMES_DE_SEGREDO, PASTAS_DE_SEGREDO), e o contracts.py, que o aberturas_plugins importa; um kit da
# raiz com outras listas aplicaria, no abertura preparar, outra regra de segredo sem aviso.
VALIDADOR = ("fundacao/core/aberturas.py", "fundacao/core/aberturas_regras.py", "fundacao/core/aberturas_plugins.py",
             "fundacao/core/aberturas_disco.py", "fundacao/core/aberturas_markdown.py", "fundacao/core/manutencao.py",
             "fundacao/core/contracts.py")
PRAZO_DA_ASSINATURA = 600  # segundos: o titular digita a senha da chave
# A cópia protegida (os caminhos de core/aberturas.FERRAMENTA_WINDOWS e FERRAMENTA_POSIX, conferidos iguais por teste).
COPIA_PROTEGIDA = {"nt": r"C:\ProgramData\FundacaoIA\ferramentas", "posix": "/usr/local/lib/fundacao-ia"}
ESQUEMA_HASHES = "fundacao.ferramenta_titular/1"
LINHAS_DA_SESSAO, LARGURA_DA_SESSAO = 12, 70  # faixas por campo e colunas por faixa (caractere largo conta 2)
AVISO_FORA_DA_COPIA = ("esta cópia da ferramenta não está na área protegida ({base}): uma sessão do Windows (sem "
                       "sandbox) ou um comando de sessão com a raiz em /mnt/e consegue alterá-la (contratos do lote 2, "
                       "§0), e uma cópia alterada pode mostrar uma ficha e assinar outra. Para valer, assine pela cópia "
                       "protegida, com o comando fixo que o kit mostra.")
_SUBSTITUTA_DE_NOME = 0x20000000  # Windows: junção, link simbólico e afins (bit 29 da etiqueta de reparse)
# Direitos que, concedidos a esta conta, deixam alterar a cópia (a sondagem de core/decisoes.conferir_ancora).
_NO_ARQUIVO = (("GENERIC_WRITE", 0x40000000), ("WRITE_DAC", 0x00040000), ("WRITE_OWNER", 0x00080000),
               ("DELETE", 0x00010000))
_NA_PASTA = (("ADD_FILE", 0x0002), ("ADD_SUBDIRECTORY", 0x0004), ("DELETE_CHILD", 0x0040), ("WRITE_DAC", 0x00040000),
             ("WRITE_OWNER", 0x00080000), ("DELETE", 0x00010000))
_ACIMA = (("WRITE_DAC", 0x00040000), ("WRITE_OWNER", 0x00080000), ("DELETE", 0x00010000), ("DELETE_CHILD", 0x0040))
# O ambiente do ssh-keygen: só o que ele usa (reconferência do pacote, 01/11/2026). O resto do ambiente do titular uma
# sessão pode ter plantado (no Windows, em HKCU\Environment): SSH_SK_PROVIDER e SSH_SK_HELPER escolhem o que roda numa
# chave sk-*, e o SSH_ASKPASS pediria a senha fora do terminal.
AMBIENTE_DO_KEYGEN = {"nt": ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "USERNAME",
                             "USERDOMAIN", "TEMP", "TMP", "LOCALAPPDATA", "APPDATA", "PROGRAMDATA", "COMPUTERNAME"),
                      "posix": ("HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TMPDIR")}
ESPERA_FINAL = "Tecle Enter para terminar (a janela aberta só para a ferramenta fecha em seguida). "


class Recusa(Exception):
    """Recusa com o motivo para o titular: nada foi assinado nem gravado."""


# ------------------------------------------------------------------ a cópia protegida, antes de importar o kit
def _ligacao(st: os.stat_result) -> bool:
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_reparse_tag", 0) & _SUBSTITUTA_DE_NOME)


def _ler_da_copia(caminho: Path, teto: int) -> bytes:
    st = os.lstat(caminho)
    if _ligacao(st) or not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size > teto:
        raise Recusa(f"{caminho} da cópia protegida é ligação, vínculo físico, não é arquivo comum ou passa do teto")
    with open(caminho, "rb") as arquivo:  # a área só o administrador (ou root) grava: sem corrida com a sessão
        return arquivo.read(teto + 1)


def _arquivos_da_copia(raiz: Path) -> tuple[list[Path], list[Path]]:
    """(arquivos, pastas) da cópia: a ferramenta e cada arquivo de assets/fundacao-kit/fundacao/**, sem atravessar
    ligação. Em assets/fundacao-kit só pode haver `fundacao` (a pasta vai para o sys.path)."""
    kit_da_copia = raiz / "assets" / "fundacao-kit"
    if sorted(os.listdir(kit_da_copia)) != ["fundacao"]:
        raise Recusa(f"{kit_da_copia} da cópia protegida tem mais que a pasta fundacao")
    arquivos, pastas, pilha = [raiz / "assets" / "host" / "fundacao_titular.py"], [], [kit_da_copia / "fundacao"]
    while pilha:
        pasta = pilha.pop()
        if _ligacao(os.lstat(pasta)):
            raise Recusa(f"ligação na cópia protegida: {pasta}")
        pastas.append(pasta)
        for nome in sorted(os.listdir(pasta)):
            st = os.lstat(pasta / nome)
            if _ligacao(st):
                raise Recusa(f"ligação na cópia protegida: {pasta / nome}")
            (pilha if stat.S_ISDIR(st.st_mode) else arquivos).append(pasta / nome)
    return arquivos, pastas


def _problemas_de_dono_posix(caminhos) -> list[str]:
    """POSIX: os caminhos sem dono root ou com escrita de grupo ou de outros (lstat)."""
    return [str(c) for c in caminhos if (lambda st: st.st_uid != 0 or st.st_mode & 0o022)(os.lstat(c))]


def _direitos_concedidos_windows(pedidos) -> list[str]:
    """Windows: os direitos que ESTA conta consegue abrir em cada caminho (pede e fecha na hora, sem alterar nada; a
    sondagem de core/decisoes, repetida aqui porque roda antes de importar o kit)."""
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                                wintypes.DWORD, wintypes.HANDLE]
    invalido, concedidos = wintypes.HANDLE(-1).value, []
    for caminho, direitos in pedidos:
        for nome, acesso in direitos:
            h = k32.CreateFileW(str(caminho), acesso, 0x7, None, 3, 0x02000000, None)  # OPEN_EXISTING, também pasta
            if h != invalido:
                k32.CloseHandle(h)
                concedidos.append(f"{nome} em {caminho}")
    return concedidos


def conferir_copia(aqui: Path | None = None) -> dict:
    """A cópia desta ferramenta, ANTES de importar o kit (ver o módulo). Na área protegida, confere o hashes.json
    (esquema e versão igual à da pasta), o SHA-256 desta ferramenta e de cada arquivo do kit ao lado (nenhum a mais nem
    a menos), o dono e os direitos e o Python que roda: qualquer diferença, Recusa. Fora dela: protegida falso e o
    aviso que a tela mostra."""
    aqui, base = Path(aqui or AQUI), Path(COPIA_PROTEGIDA["nt" if os.name == "nt" else "posix"])
    try:
        rel = aqui.relative_to(base)
    except ValueError:
        return {"protegida": False, "aviso": AVISO_FORA_DA_COPIA.format(base=base)}
    if len(rel.parts) != 3 or rel.parts[1:] != ("assets", "host"):
        raise Recusa(f"a ferramenta está em {aqui}, fora da forma da cópia protegida (<versão>/assets/host)")
    versao, raiz = rel.parts[0], base / rel.parts[0]
    try:
        hashes = json.loads(_ler_da_copia(raiz / "hashes.json", 1 << 20).decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise Recusa(f"o hashes.json da cópia protegida está ausente ou ilegível ({exc.__class__.__name__})") from None
    esperados = hashes.get("arquivos") if isinstance(hashes, dict) else None
    if (not isinstance(esperados, dict) or hashes.get("schema_version") != ESQUEMA_HASHES
            or hashes.get("versao") != versao):
        raise Recusa(f"o hashes.json da cópia protegida está fora da forma ({ESQUEMA_HASHES}, versão {versao})")
    arquivos, pastas = _arquivos_da_copia(raiz)
    calculados = {c.relative_to(raiz).as_posix(): hashlib.sha256(_ler_da_copia(c, 16 << 20)).hexdigest()
                  for c in arquivos}
    diferentes = sorted(n for n in set(calculados) | set(esperados) if calculados.get(n) != esperados.get(n))
    if diferentes:
        raise Recusa("a cópia protegida não confere com o hashes.json: " + ", ".join(diferentes[:5]))
    python = Path(os.path.realpath(sys.executable))
    if os.name == "nt":
        registrado = hashes.get("python") if isinstance(hashes.get("python"), dict) else {}
        try:
            mesmo = os.path.samefile(python, registrado.get("caminho", ""))
            mesmo = mesmo and hashlib.sha256(python.read_bytes()).hexdigest() == registrado.get("sha256")
        except (OSError, TypeError, ValueError):
            mesmo = False
        if not mesmo:
            raise Recusa("rode a ferramenta com o Python fixado da cópia protegida (o do comando que o kit mostra)")
        problemas = _direitos_concedidos_windows(
            [(c, _NO_ARQUIVO) for c in (*arquivos, raiz / "hashes.json", python)]
            + [(p, _NA_PASTA) for p in (*pastas, raiz, raiz / "assets", raiz / "assets" / "host",
                                        raiz / "assets" / "fundacao-kit")]
            + [(p, _ACIMA) for p in raiz.parents])
    else:
        problemas = _problemas_de_dono_posix([*arquivos, raiz / "hashes.json", *pastas, raiz, raiz / "assets",
                                              raiz / "assets" / "host", raiz / "assets" / "fundacao-kit",
                                              *raiz.parents, python, *python.parents])
    if problemas:
        raise Recusa("a cópia protegida (ou o Python) pode ser alterada por esta conta: " + "; ".join(problemas[:4]))
    return {"protegida": True, "versao": versao, "raiz": str(raiz)}


def kit() -> SimpleNamespace:
    """Os módulos do kit desta cópia, nunca os da raiz."""
    if str(KIT) not in sys.path:
        sys.path.insert(0, str(KIT))
    from fundacao.core import (aberturas, aberturas_disco, aberturas_plugins, aberturas_regras, contracts, decisoes,
                               publicacao)
    if not Path(aberturas.__file__).resolve().is_relative_to(KIT.resolve()):
        raise Recusa("o kit carregado não é o desta skill: rode com python -I -B -S, fora da pasta da raiz")
    return SimpleNamespace(aberturas=aberturas, regras=aberturas_regras, plugins=aberturas_plugins,
                           disco=aberturas_disco, contracts=contracts, decisoes=decisoes, publicacao=publicacao)


def conferir_kit_da_raiz(raiz: Path, k: SimpleNamespace) -> None:
    """O validador do kit da raiz é idêntico ao desta ferramenta (lido sem seguir ligação, sem executar nada da raiz)."""
    with k.disco.Pasta(raiz, ("fundacao", "core")) as core:
        for rel in VALIDADOR:
            try:
                da_raiz = core.ler(rel.rpartition("/")[2], 1 << 20)
            except OSError as exc:
                raise Recusa(f"{rel} do kit da raiz não foi lido sem seguir ligação ({exc})") from None
            if da_raiz is None:
                raise Recusa(f"o kit da raiz não tem {rel}: atualize a fundação para a versão desta skill "
                             "(scripts/atualizar_fundacao.py)")
            if da_raiz != (KIT / rel).read_bytes():
                raise Recusa(f"{rel} do kit da raiz difere do desta ferramenta: atualize a fundação, ou use a "
                             "ferramenta da mesma versão do kit da raiz")


def _ancora_protegida_windows(ancora: Path) -> list[str]:
    """Windows, SEM processo filho (revisão do pacote, 31/10/2026): a âncora e cada pasta acima não são ligação e esta
    conta não as altera. Não chama decisoes.conferir_ancora, que no Windows roda powershell.exe e icacls pelo nome nu
    (CreateProcess procura primeiro na pasta atual, onde uma cópia plantada rodaria como o titular no meio da
    cerimônia). As sondas aqui (ctypes CreateFileW e os.lstat) não abrem processo nenhum."""
    problemas = []
    for p in (ancora, *ancora.parents):
        try:
            if _ligacao(os.lstat(p)):
                problemas.append(f"ligação no caminho da âncora: {p}")
        except OSError as exc:
            problemas.append(f"{p} ilegível ({exc.__class__.__name__})")
    return problemas + _direitos_concedidos_windows(
        [(ancora, _NO_ARQUIVO), (ancora.parent, _NA_PASTA)] + [(p, _ACIMA) for p in ancora.parent.parents])


def conferir_ancora_antes(chave: Path, ancora, k: SimpleNamespace, *, exigir_protegida: bool = False) -> None:
    """Antes de pedir a senha: a âncora existe (na cópia protegida, também protegida contra esta conta) e, pela chave
    pública ao lado da privada, aceita esta chave no namespace fundacao-abertura. Sem a .pub, a conferência da chave
    fica para depois de assinar (antes de gravar). A prova da proteção da âncora não abre processo filho: no Windows,
    sondas em processo (_ancora_protegida_windows); no POSIX, decisoes.conferir_ancora, que lá não roda nada."""
    try:
        ancora = k.decisoes.resolver_ancora(ancora)
    except k.decisoes.DecisaoInvalida as exc:
        raise Recusa(str(exc)) from None
    if ancora is None or not Path(ancora).is_file():
        raise Recusa("âncora ausente nesta máquina: crie-a com o preparar-maquina.ps1 (passo do titular, com UAC)")
    if exigir_protegida:
        if os.name == "nt":
            problemas = _ancora_protegida_windows(Path(ancora))
            motivo = "esta conta pode alterá-la: " + "; ".join(problemas[:4]) if problemas else None
        else:
            sondagem = k.decisoes.conferir_ancora(ancora)
            motivo = None if sondagem.get("protegida") else sondagem.get("motivo")
        if motivo is not None:
            raise Recusa(f"a âncora não está protegida ({motivo}): refaça o passo dela no preparar-maquina.ps1 "
                         "(com UAC) antes de assinar")
    try:
        impressao = k.decisoes.impressao_digital(Path(str(chave) + ".pub").read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError):
        impressao = None
    if impressao is None:
        return
    linhas = [li for li in k.decisoes.ler_ancora(ancora) if li["impressao_digital"] == impressao]
    if not linhas:
        raise Recusa(f"a chave {chave.name} não está na âncora: confira o --chave ou atualize a âncora com o "
                     "preparar-maquina.ps1")
    if not any(k.aberturas.namespace_permitido(li["namespaces"], k.aberturas.NAMESPACE) for li in linhas):
        raise Recusa(f"a âncora limita a chave a {','.join(linhas[0]['namespaces'] or [])} e não inclui "
                     f"{k.aberturas.NAMESPACE}: atualize a âncora com o preparar-maquina.ps1 (passo do titular, com "
                     "UAC) e rode de novo")


def ambiente_do_keygen(exe: str, pasta: Path) -> dict:
    """O ambiente mínimo do ssh-keygen (AMBIENTE_DO_KEYGEN), com o PATH só do sistema e o SSH_AUTH_SOCK num caminho que
    não existe, para a chave carregada num ssh-agent não assinar sem a senha."""
    ambiente = {c: os.environ[c] for c in AMBIENTE_DO_KEYGEN["nt" if os.name == "nt" else "posix"] if c in os.environ}
    pasta_do_exe = Path(exe).parent
    ambiente["PATH"] = os.pathsep.join((str(pasta_do_exe), str(pasta_do_exe.parent)) if os.name == "nt"
                                       else ("/usr/bin", "/bin"))
    ambiente["SSH_AUTH_SOCK"] = str(Path(pasta) / "sem-agente")
    return ambiente


def assinar(exe: str, chave: Path, conteudo: bytes, namespace: str) -> bytes:
    """`ssh-keygen -Y sign` sobre uma cópia privada dos bytes conferidos, com o ambiente mínimo (ambiente_do_keygen).
    A senha vai direto do terminal ao ssh-keygen."""
    with tempfile.TemporaryDirectory(prefix="fundacao-titular-") as pasta:
        alvo = Path(pasta) / "ficha.json"
        alvo.write_bytes(conteudo)
        ambiente = ambiente_do_keygen(exe, Path(pasta))
        r = subprocess.run([exe, "-Y", "sign", "-f", str(chave), "-n", namespace, str(alvo)], env=ambiente,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=PRAZO_DA_ASSINATURA)
        sig = Path(str(alvo) + ".sig")
        if r.returncode != 0 or not sig.is_file():
            raise Recusa("o ssh-keygen não assinou (chave ausente, senha errada ou cancelado): "
                         + r.stderr.decode("utf-8", "replace").strip()[-300:])
        return sig.read_bytes()


def _quebrar_em_faixas(linha: str, teto: int) -> list[str]:
    """`linha` em faixas de até `teto` colunas, contando 2 colunas para caractere largo (east_asian_width W ou F): uma
    linha longa não quebra no terminal fora da marca (revisão do pacote, 31/10/2026)."""
    faixas, atual, larg = [], "", 0
    for ch in linha:
        w = 2 if unicodedata.east_asian_width(ch) in "WF" else 1
        if atual and larg + w > teto:
            faixas.append(atual)
            atual, larg = "", 0
        atual, larg = atual + ch, larg + w
    if atual or not faixas:
        faixas.append(atual)
    return faixas


def texto_da_sessao(texto: str) -> list[str]:
    """O texto da sessão para a tela, em faixas: cada linha quebrada em até LARGURA_DA_SESSAO colunas (caractere largo
    conta 2), SEM linhas vazias seguidas, cada FAIXA marcada com '    | ' e contando para o teto de LINHAS_DA_SESSAO
    por campo; o que passar fica de fora, com o aviso do corte. Assim uma linha longa não transborda no terminal sem
    a marca — onde a sessão poderia imitar uma linha do bloco fixo (revisão do pacote, 31/10/2026)."""
    fontes = []
    for linha in str(texto).expandtabs(4).splitlines():
        if linha.strip() or (fontes and fontes[-1].strip()):
            fontes.append(linha)
    faixas = [faixa for linha in fontes for faixa in _quebrar_em_faixas(linha, LARGURA_DA_SESSAO)]
    saida = ["    | " + faixa for faixa in faixas[:LINHAS_DA_SESSAO]]
    if len(faixas) > LINHAS_DA_SESSAO:
        saida.append(f"    [texto da sessão cortado: {len(faixas) - LINHAS_DA_SESSAO} linhas]")
    return saida


def _mostrar_ficha(escrever, projeto: str, versao: int, ficha: dict, avisos: list, anterior: dict,
                   k: SimpleNamespace, aviso_da_copia: str | None = None) -> None:
    """A tela antes da pergunta: primeiro o texto da sessão, cortado e marcado; depois, até a pergunta, só texto fixo
    desta ferramenta. Assim o que a sessão escreve nunca fica entre a lista verdadeira e a pergunta, nem a empurra
    para fora da tela (revisão do pacote, 31/10/2026)."""
    escrever(f"Ficha de aberturas do projeto {projeto}, versão {versao} (identificador {ficha['ficha_id']}).")
    escrever("Texto escrito pela sessão (pode não ser o que você pediu; o que vale é a lista fixa logo abaixo):")
    for chave, rotulo in (("motivo", "  Motivo (confira se são as suas palavras):"), ("consequencias",
                                                                                     "  Consequências:")):
        escrever(rotulo)
        for linha in texto_da_sessao(ficha[chave]):
            escrever(linha)
    escrever("---- Daqui até a pergunta, só texto fixo desta ferramenta ----")
    escrever(f"O que a v{versao} de {projeto} abre:")
    for i, item in enumerate(k.regras.descrever(ficha), 1):
        escrever(f"  {i}. {item['texto']}")
    agora = set(k.regras.itens(ficha))
    antes = set(k.regras.itens(anterior["ficha"])) if anterior["valida"] else set()
    escrever("Comparada com " + (f"a v{anterior['versao']} já assinada:" if anterior["valida"]
                                 else "nada (nenhuma ficha assinada valendo):"))
    escrever("  passa a abrir: " + (", ".join(f"{s} {i}" for s, i in sorted(agora - antes)) or "nada"))
    escrever("  deixa de abrir: " + (", ".join(f"{s} {i}" for s, i in sorted(antes - agora)) or "nada"))
    escrever(f"Vale até {ficha['vigencia_ate']}: vencida, fecha tudo." if "vigencia_ate" in ficha
             else "Sem data de validade: vale até uma versão nova assinada.")
    for aviso in avisos:
        escrever(f"  Aviso ({aviso.get('dominio') or aviso['campo']}): {aviso['motivo']}")
    if aviso_da_copia:
        escrever("Atenção: " + aviso_da_copia)
    escrever("Importante: " + k.aberturas.HONESTIDADE)


def _ficha_preparada(raiz: Path, projeto: str, versao, hoje: date, k: SimpleNamespace) -> tuple:
    """(versão, ficha, problemas, bytes canônicos) da ficha preparada, conferida de novo inteira; senão, Recusa."""
    with k.disco.Pasta(raiz, ("projects", projeto)) as pasta_do_projeto:
        if not pasta_do_projeto.existe:
            raise Recusa(f"o projeto {projeto} não tem pasta nesta raiz")
    with k.disco.Pasta(raiz, ("projects", projeto, *k.aberturas.RASCUNHOS)) as rascunhos:
        presentes = k.aberturas.versoes(rascunhos.nomes())
        versao = versao or (max(presentes) if presentes else None)
        if versao not in presentes:
            raise Recusa("nenhuma ficha preparada com essa versão em outputs/aberturas/ (a sessão prepara com: python "
                         "-m fundacao abertura preparar)")
        try:
            bruto = rascunhos.ler(presentes[versao], k.regras.TETO_FICHA)
        except k.disco.LeituraRecusada as exc:
            raise Recusa(f"a ficha preparada foi recusada ({exc})") from None
    try:
        ficha = k.regras.carregar(bruto or b"")
    except ValueError as exc:
        raise Recusa(f"ficha ilegível: {exc}") from None
    problemas = k.regras.validar(ficha, projeto=projeto, hoje=hoje)
    erros = list(problemas["erros"])
    if isinstance(ficha, dict) and ficha.get("versao") != versao:
        erros.append({"campo": "versao", "motivo": "a versão escrita na ficha difere da do nome do arquivo"})
    for item in (ficha.get("plugins") if not erros else None) or []:
        erros += k.plugins.conferir_plugin(raiz / "projects" / projeto, item)["erros"]
    if erros:
        detalhe = "; ".join(f"{e['campo']}: {e['motivo']}" for e in erros[:8])
        raise Recusa(f"a ficha v{versao} não passa nos tetos fixos ({detalhe}): nada foi assinado")
    return versao, ficha, problemas, k.regras.canonico(ficha)


def _assinar_ficha(k, raiz: Path, projeto: str, versao, chave, confirmar, escrever, ancora, hoje: date,
                   copia: dict) -> int:
    conferir_kit_da_raiz(raiz, k)
    versao, ficha, problemas, conteudo = _ficha_preparada(raiz, projeto, versao, hoje, k)
    caixa, partes_da_caixa = k.aberturas.caixa_de_entrada(raiz, projeto), k.aberturas.partes_da_caixa(projeto)
    with k.disco.Pasta(raiz, partes_da_caixa) as aberta:
        assinadas, igual = k.aberturas.versoes(aberta.nomes()), False
    if versao in assinadas:
        atual = k.aberturas.conferir_versao(caixa, versao, projeto, hoje=hoje, ancora=ancora)
        if atual["sha256"] is None:
            raise Recusa(f"a v{versao} da caixa de entrada não foi lida ({atual['motivo_invalida']})")
        if atual["sha256"] != hashlib.sha256(conteudo).hexdigest():
            raise Recusa(f"a caixa de entrada já tem a v{versao} com outro conteúdo: prepare uma versão nova")
        if atual["valida"]:
            escrever(f"A v{versao} de {projeto} já está assinada, igual a esta, na caixa de entrada: nada a fazer.")
            return 0
        igual = True  # a mesma ficha com a assinatura ausente ou inválida: assina de novo e troca só o .sig
    if versao < max(assinadas, default=0):
        raise Recusa(f"versão menor que a maior já assinada (v{max(assinadas)}): prepare uma versão nova")
    if os.name != "nt":
        instaladas = k.aberturas.listar_versoes(k.aberturas.AREA_DO_TITULAR.format(projeto=projeto))
        if versao <= max(instaladas, default=0):
            raise Recusa(f"a área do titular já tem a v{max(instaladas)} instalada: prepare uma versão maior")
    chave = Path(chave).expanduser() if chave else Path.home() / ".ssh" / k.decisoes.CHAVE_DO_TITULAR
    conferir_ancora_antes(chave, ancora, k, exigir_protegida=copia["protegida"])
    exe = k.decisoes.ssh_keygen_do_sistema()
    if not exe:
        raise Recusa("OpenSSH do sistema ausente: a ferramenta só assina com o ssh-keygen do sistema")
    anterior = k.aberturas.vigente(raiz, projeto, caixa, hoje=hoje, ancora=ancora)
    if os.name != "nt":  # no Ubuntu, a que vale é a instalada na área do titular
        instalada = k.aberturas.vigente(raiz, projeto, k.aberturas.AREA_DO_TITULAR.format(projeto=projeto), hoje=hoje,
                                        ancora=ancora)
        if instalada["valida"] and (not anterior["valida"] or instalada["versao"] >= anterior["versao"]):
            anterior = instalada
    _mostrar_ficha(escrever, projeto, versao, ficha, problemas["avisos"], anterior, k, copia.get("aviso"))
    try:
        resposta = confirmar(f"Para assinar a v{versao} de {projeto}, digite o nome do projeto ({projeto}) e Enter; "
                             "qualquer outra coisa cancela: ")
    except (EOFError, KeyboardInterrupt):
        resposta = None
    if (resposta or "").strip() != projeto:
        escrever("Cancelado: nada foi assinado nem gravado.")
        return 1
    sig = assinar(exe, chave, conteudo, k.aberturas.NAMESPACE)
    conferida = k.aberturas.conferir_assinatura(conteudo, sig, ancora)
    if not conferida["ok"]:
        raise Recusa(f"a assinatura feita não confere ({conferida['motivo']}): nada foi gravado")
    nome = k.aberturas.nome_da_ficha(versao)
    with k.disco.Pasta(raiz, partes_da_caixa, criar=True) as pasta_caixa:
        pasta_caixa.trocar(nome + ".sig", sig)  # a assinatura antes: a ficha só aparece com ela ao lado
        if not igual:
            pasta_caixa.criar_novo(nome, conteudo)
    escrever(f"Assinada pela chave de {conferida['assinante']} ({conferida['impressao_digital']}) e gravada em "
             f"{caixa / nome}.")
    escrever("Próximo passo: no Ubuntu, rode o preparo do projeto (sudo), que instala a ficha na área do titular, e "
             f"confira que ele instala a v{versao}. No Windows, a caixa de entrada não vale como área do titular.")
    return 0


def assinar_ficha(raiz, projeto: str, *, versao: int | None = None, chave=None, confirmar=None, saida=None,
                  ancora=None, hoje: date | None = None) -> int:
    """`assinar-ficha` (ver o módulo). `confirmar(texto) -> resposta`: injetado nos testes; sem ele, exige terminal
    interativo e usa input(). `ancora` e `hoje`: para ensaio (a âncora padrão desta máquina, se existir, vence)."""
    copia = conferir_copia()  # antes de importar o kit
    k = kit()
    saida = saida or sys.stdout
    if not isinstance(projeto, str) or not k.regras.ID_PROJETO.fullmatch(projeto) or "--" in projeto:
        raise Recusa("identificador de projeto inválido")
    if confirmar is None:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            raise Recusa("sem terminal interativo: rode fora do Claude, pela caixa Executar (Win+R) ou num terminal (a "
                         "ferramenta pede que você digite o nome do projeto)")
        confirmar = input
    try:
        return _assinar_ficha(k, Path(os.path.abspath(raiz)), projeto, versao, chave, confirmar,
                              lambda texto="": saida.write(texto + "\n"), ancora, hoje or date.today(), copia)
    except k.contracts.FundacaoError as exc:
        raise Recusa(str(exc)) from None


def verificar_ficha(raiz, projeto: str, *, versao: int | None = None, saida=None, ancora=None,
                    hoje: date | None = None) -> int:
    """`verificar-ficha`: a ficha em vigor (ou a da `versao`) na caixa de entrada e, no Linux, na área do titular. O
    código segue a que conta neste sistema: no Linux, a instalada; no Windows, a da caixa de entrada."""
    copia = conferir_copia()
    k = kit()
    aberturas = k.aberturas
    if not isinstance(projeto, str) or not k.regras.ID_PROJETO.fullmatch(projeto) or "--" in projeto:
        raise Recusa("identificador de projeto inválido")
    raiz, saida = Path(os.path.abspath(raiz)), saida or sys.stdout
    caixa = aberturas.caixa_de_entrada(raiz, projeto)
    if versao:
        res = {"caixa_de_entrada": aberturas.conferir_versao(caixa, versao, projeto, hoje=hoje, ancora=ancora)}
    else:
        res = {"caixa_de_entrada": aberturas.vigente(raiz, projeto, caixa, hoje=hoje, ancora=ancora)}
    conta = res["caixa_de_entrada"]
    if os.name != "nt":
        res["area_do_titular"] = conta = aberturas.vigente(raiz, projeto,
                                                           aberturas.AREA_DO_TITULAR.format(projeto=projeto),
                                                           hoje=hoje, ancora=ancora)
    res["copia_da_ferramenta"] = copia
    res["importante"] = aberturas.HONESTIDADE
    saida.write(json.dumps(res, ensure_ascii=False, indent=2) + "\n")
    return 0 if conta["valida"] else 3


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fundacao_titular.py", allow_abbrev=False,
                                description="Ferramenta fixa do titular: assina e confere a ficha de aberturas.")
    sub = p.add_subparsers(dest="acao", required=True)
    for nome in ("assinar-ficha", "verificar-ficha"):
        a = sub.add_parser(nome, allow_abbrev=False)
        a.add_argument("--raiz", required=True, help="raiz da fundação")
        a.add_argument("--projeto", required=True)
        a.add_argument("--versao", type=int, help="padrão: a maior preparada (assinar) ou a em vigor (verificar)")
        if nome == "assinar-ficha":
            a.add_argument("--chave", help="chave privada do titular (padrão: ~/.ssh/fundacao_titular)")
    return p


def esperar_enter() -> None:
    """Com terminal (entrada e saída), espera um Enter antes de sair: pela caixa Executar (Win+R), a janela fecha com a
    ferramenta, e o titular perderia o resultado (assinada, cancelada, a recusa ou o erro) e o próximo passo
    (reconferência do pacote, 01/11/2026). Sem terminal (saída redirecionada, teste), não espera."""
    try:
        if sys.stdin.isatty() and sys.stdout.isatty():
            input("\n" + ESPERA_FINAL)
    except (EOFError, KeyboardInterrupt, AttributeError, OSError, ValueError):
        pass


def main(argv: list[str] | None = None) -> int:
    if os.name == "nt":  # antes de qualquer processo filho: CreateProcess não procura executável na pasta atual
        os.environ["NoDefaultCurrentDirectoryInExePath"] = "1"  # (uma cópia plantada de powershell/icacls rodaria aqui)
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    try:
        codigo = _rodar(construir_parser().parse_args(argv))
    except SystemExit as exc:  # o argparse já escreveu a ajuda (código 0) ou o erro de argumento (2)
        codigo = exc.code if isinstance(exc.code, int) else 2
    except Exception:  # erro inesperado: o detalhe fica na tela até o Enter, em vez de sumir com a janela
        traceback.print_exc()
        codigo = 2
    esperar_enter()
    return codigo


def _rodar(args) -> int:
    try:
        if args.acao == "assinar-ficha":
            return assinar_ficha(args.raiz, args.projeto, versao=args.versao, chave=args.chave)
        return verificar_ficha(args.raiz, args.projeto, versao=args.versao)
    except Recusa as exc:
        sys.stderr.write(f"Recusado: {exc}\n")
        return 2
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        sys.stderr.write(f"Recusado ({exc.__class__.__name__}): {exc}\n")
        return 2
    except KeyboardInterrupt:
        sys.stderr.write("Cancelado pelo titular: confira com verificar-ficha o que ficou na caixa de entrada.\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
