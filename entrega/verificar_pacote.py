#!/usr/bin/env python3
"""Confere que os pacotes versionados em entrega/dist são EXATAMENTE a árvore da skill (auditoria Codex Security da
1.7.6, #6). Só biblioteca padrão; não altera nada e não executa nada da árvore.

  python entrega/verificar_pacote.py [--dist <pasta>] [--skill <pasta>] [--exigir-igual-a-arvore]
                                     [--exigir-transferencia] [--lista-so-cresce] [--exigir-transferencia-fixada]

Confere, sempre:
- o SHA256SUMS.txt: uma linha para cada pacote e nenhuma outra, com o SHA-256 dos bytes que estão em dist/; o
  EMPACOTAMENTO.json com os mesmos hashes, a contagem de arquivos de cada pacote e a versão de dentro deles;
- cada pacote, lido uma vez: zip íntegro (CRC), só arquivos comuns sob `fundacao-ia-multiprojetos/` (nenhuma pasta,
  link simbólico ou modo especial; nenhum nome vazio, `.`, `..`, absoluto ou com barra invertida), sem cifra,
  compressão stored ou deflate, sem nome repetido (também por maiúsculas/minúsculas ou forma Unicode), até 10.000
  entradas e 100 MiB descompactados, e nenhum byte fora das entradas — antes, entre ou depois delas, nem
  comentário —, para que qualquer leitor de zip veja os mesmos membros conferidos;
- os dois pacotes entre si: o .skill é o completo menos o que o package_skill.py do skill-creator deixa de fora, com
  os mesmos bytes;
- dist/anteriores/: cada conjunto guardado confere com o SHA256SUMS.txt dele, os zips estão íntegros e a versão de
  dentro é a da pasta (a fonte de cada época não está na árvore para comparar); e cada pacote está, com esse hash, na
  lista dos pacotes liberados, entrega/HISTORICO-PACOTES-SHA256.txt (`<sha256>  <versão>/<arquivo>`, gerada do que
  existia na 1.7.7; o empacotar.py acrescenta os pacotes novos). Um conjunto novo, coerente consigo mesmo, não passa
  mais; a mesma `<versão>/<arquivo>` com dois hashes também não (revisão de segurança da 1.7.7, R177-ATU-04).

E compara os dois pacotes com a árvore da skill: o .skill tem de ter exatamente os arquivos que o package_skill.py
leva (sem evals/ na raiz, __pycache__, node_modules, *.pyc e .DS_Store) e o completo, exatamente os da pasta (sem
__pycache__ e *.pyc): mesmos nomes, mesmos bytes, nenhum a mais ou a menos; ligação na árvore impede a comparação
(o zip publicaria o alvo dela). Os bits de permissão não entram: dependem do sistema que gerou o pacote (no Windows,
0o666) e o zipfile, que o instalador usa, não os aplica.

Intervalo de preparo: o pacote só é gerado na liberação, e a árvore muda antes dela. Sem opção (árvore de
desenvolvimento e testes da entrega), a comparação com a árvore é relatada em `fonte` e não reprova. Com
--exigir-igual-a-arvore (a CI pública, que só recebe commits de liberação, e a liberação depois de empacotar), a
árvore tem de ser a do pacote: a mesma versão no SKILL.md e os mesmos arquivos, byte a byte; e os pacotes de dist/
têm de estar na lista dos liberados.

--exigir-transferencia (a CI pública e a etapa 03 da liberação, que monta a transferência depois do empacotamento e
da conferência rígida da etapa 02 e a confere antes e depois de acrescentar a linha dela à lista): em
entrega/transferencia/, o `<nome>-<versão>-para-claude-ai.zip` da versão de dist/ existe e é byte a byte o .skill de
dist/ (é ele que o README manda enviar ao claude.ai), e o `<nome>-<versão>.zip` passa pelo `examinar_zip` e leva
exatamente LEIA-ME.txt, o .skill igual, o instalar_skill.py igual ao de entrega/ e um SHA256SUMS.txt coerente com
eles; de toda versão anterior, o .skill do -para-claude-ai.zip e o de dentro do zip principal estão na lista; outro
arquivo na pasta reprova (o -para-revisao.md, texto para revisão, não é conferido). O zip principal também vai para a
lista (`<sha256>  <versão>/<nome>-<versão>.zip`; segunda passada da revisão de segurança da 1.7.7, R177B-B-07), o que
prende o LEIA-ME e o instalador que viajam com o .skill: o de toda versão anterior tem de estar nela com o mesmo
hash; o da versão de dist/, se estiver, também; e todo zip principal da lista tem de estar na pasta (transferência
publicada não sai; terceira passada, R177C-B-05). O LEIA-ME da versão de dist/ é conferido pela forma
(`conferir_leia_me`) com ou sem a linha dele (a liberação a acrescenta ao montar a transferência; na CI, ela pode ter
vindo no mesmo commit que o zip; terceira passada, R177C-B-05): só manda rodar o instalador (instalar, atualizar,
verificar ou remover, com --origem do .skill, --sha256 e --confirmar), a conferência do hash e a cópia do .skill para
.zip, e fora disso não chama programa conhecido nem caminho ou nome com extensão de programa (`manda_rodar`); todo
hash citado é o do .skill de dist/; endereço, só http(s) de claude.com, claude.ai ou anthropic.com, com o host lido
como o navegador o lê, e nem outro esquema, nem www. ou domínio com caminho sem esquema; nenhum caractere de
controle, de formatação, não atribuído ou invisível. A forma não lê a frase: instrução só em palavras e hash escrito
em grupos passam.
--exigir-transferencia-fixada (só a CI pública, que roda depois da etapa 03): o mesmo, e a linha do zip principal da
versão de dist/ tem de estar na lista (R177C-B-05). A liberação não a usa: antes de acrescentar a linha, ela confere a
transferência pela forma do LEIA-ME.
--lista-so-cresce (só a CI pública, com a história inteira do git: fetch-depth 0): cada versão da lista nos commits
que a tocaram está contida na atual — linha antiga trocada ou tirada reprova.

Saída em JSON. Códigos: 0 confere · 1 diverge · 2 uso incorreto.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import io
import json
import os
import re
import stat
import struct
import subprocess
import sys
import unicodedata
import zipfile
import zlib
from pathlib import Path, PurePosixPath

RAIZ = Path(__file__).resolve().parents[1]
SKILL = RAIZ / "fundacao-ia-multiprojetos"
DIST = RAIZ / "entrega" / "dist"
NOME = "fundacao-ia-multiprojetos"
PACOTE = f"{NOME}.skill"
COMPLETO = f"{NOME}-completo.zip"
# O que o package_skill.py do skill-creator deixa fora do .skill: a regra dele, presa ao hash registrado no
# empacotar.py (FERRAMENTA_ESPERADA). Se a ferramenta mudar, o empacotamento para, e esta regra é revista junto.
FORA_DO_SKILL_PASTAS = {"__pycache__", "node_modules"}  # em qualquer nível
FORA_DO_SKILL_NA_RAIZ = {"evals"}
FORA_DO_SKILL_ARQUIVOS = {".DS_Store"}
FORA_DO_SKILL_PADROES = ("*.pyc",)
COMPRESSOES = {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
BITS_PERMITIDOS = 0x0800 | 0x0006  # nome em UTF-8 e dicas de nível do deflate; nada de cifra nem descritor de dados
LIMITE_ENTRADAS = 10_000
LIMITE_BYTES = 100 * 1024 * 1024  # soma descompactada declarada (o mesmo teto do instalador)
VERSAO = re.compile(r'^\s*version:\s*"?([^"\s]+)"?\s*$', re.M)  # a mesma do empacotar.py
HISTORICO = "HISTORICO-PACOTES-SHA256.txt"  # em entrega/, ao lado de dist/: os pacotes liberados; a lista só cresce
# `<sha256>  <versão>/<arquivo>`: os dois pacotes e, desde a segunda passada da 1.7.7, o zip principal da transferência
# da mesma versão (R177B-B-07).
LINHA_DO_HISTORICO = re.compile(r"([0-9a-f]{64})  ((\d+(?:\.\d+)+)/(?:" + re.escape(PACOTE) + "|" + re.escape(COMPLETO)
                                + "|" + re.escape(NOME) + r"-\3\.zip))")
# Transferência (entrega/transferencia/): zip para outro computador, o .skill para o claude.ai e texto para revisão.
TRANSFERENCIA = re.compile(re.escape(NOME) + r"-(?P<versao>\d+(?:\.\d+)+)(?:(?P<claude>-para-claude-ai)\.zip|"
                           r"(?P<revisao>-para-revisao)\.md|\.zip)")
MEMBROS_DA_TRANSFERENCIA = ("LEIA-ME.txt", PACOTE, "instalar_skill.py", "SHA256SUMS.txt")
# LEIA-ME da transferência da versão de dist/ (R177B-B-07): o que ele pode mandar rodar (a linha inteira, depois do
# recuo e de um rótulo como "Linux:  "), as linhas que citam um programa sem mandá-lo rodar, o que faz a linha "mandar
# rodar" e os endereços que pode citar.
COMANDOS_DO_LEIA_ME = tuple(re.compile(p, re.I) for p in (
    r"get-filehash \.\\" + re.escape(PACOTE) + " -algorithm sha256",
    r"sha256sum -c sha256sums\.txt", r"shasum -a 256 -c sha256sums\.txt",
    r"(?:python3?|py) instalar_skill\.py (?:instalar|atualizar|verificar|remover)(?: --origem (?:\.[\\/])?"
    + re.escape(PACOTE) + r"| --sha256 [0-9a-f]{64}| --confirmar)*",
    r"copy-item \.\\" + re.escape(PACOTE) + r" \.\\" + re.escape(NOME) + r"\.zip",
    "cp " + re.escape(PACOTE) + " " + re.escape(NOME) + r"\.zip"))
# A linha do instalador na tabela do CONTEÚDO, a mesma desde a 1.4.0: nome com extensão de programa no texto manda
# rodar (terceira passada, R177C-B-05), e esta é a única citação dele fora dos comandos; noutra frase, "o instalador".
CITACOES_DO_LEIA_ME = (re.compile(r"instalar_skill\.py Instalador: instalar, atualizar, verificar e remover\."),)
PROGRAMAS = frozenset("""python python3 py pythonw pip pip3 pipx uv uvx conda powershell pwsh cmd bash sh zsh dash fish
wsl curl wget iwr irm iex invoke-webrequest invoke-restmethod invoke-expression invoke-item start-process saps start
msiexec certutil bitsadmin start-bitstransfer mshta rundll32 regsvr32 wscript cscript schtasks reg sudo su doas chmod
chown git npm npx node deno bun winget choco scoop brew apt apt-get dnf yum pacman set-executionpolicy set-content
add-content out-file new-item remove-item rm del erase rmdir rd mv move move-item cp copy copy-item xcopy robocopy
get-filehash sha256sum shasum open xdg-open explorer ssh scp ftp tftp nc ncat telnet perl ruby php java osascript eval
exec source echo pnpm yarn gem dotnet nuget snap flatpak zypper install-module install-package add-appxpackage runas
ksh csh tcsh sftp""".split())
# Os que também são palavras do texto ("se o comando python não existir, use py"; "move", verbo) só mandam rodar com
# parêntese ou argumento. Os demais — gerenciadores, baixadores, shells, quem roda texto como código ou mexe em arquivo
# — também com qualquer palavra depois (`pip install x`, `winget install x`) ou sozinhos no lugar de um comando
# (R177C-B-05).
PROGRAMAS_FRACOS = frozenset({"python", "python3", "py", "pythonw", "move"})
ARGUMENTO = re.compile(r"[-./\\$\"'|&<>~%]|.*[./\\:]")  # opção, caminho, variável ou operador: o programa é chamado
VERSAO_SOLTA = re.compile(r"\d+(?:\.\d+)*(?:/\d+(?:\.\d+)*)*")  # "Python 3.10", "3.10/3.11": versão, não argumento
ROTULO_DO_LEIA_ME = re.compile(r"[^\W\d_][\w ()]{0,29}:\s{2,}")  # "Linux:  ", "Windows (PowerShell):  "
HOSTS_DO_LEIA_ME = ("claude.com", "claude.ai", "anthropic.com")
# Programa pelo nome (R177C-B-05): extensão de programa, script ou instalador na última parte...
EXTENSOES_EXECUTAVEIS = frozenset("""exe com bat cmd ps1 psm1 psd1 sh bash zsh ksh csh fish command py pyw pyz msi msp
msix msixbundle appx appxbundle appinstaller vbs vbe js jse wsf wsh hta scr pif cpl msc jar lnk reg inf pl rb php run
bin app deb rpm pkg dmg appimage apk""".split())
# ... ou caminho que roda de qualquer ponto da linha: ./ .\ ../ ..\, letra de unidade, \\servidor, raiz, %VAR%\, $VAR/.
# O outro caminho com / ou \ (~/.claude/skills/<nome>, entrega/dist) só conta no lugar de um comando: começo da linha,
# depois de rótulo, de dois-pontos ou de um dos OPERADORES.
CAMINHO_EXPLICITO = re.compile(r"\.\.?[\\/]|[a-z]:[\\/]|[\\/]|%[^%\s]+%[\\/]|\$(?:env:)?\w+[\\/]|\$\{[^}\s]+\}[\\/]")
OPERADORES = frozenset({";", "&", "&&", "|", "||"})
# Endereços (R177C-B-05): esquema de duas letras ou mais com algo colado depois dos dois-pontos (só http e https valem,
# e só para os HOSTS_DO_LEIA_ME), www. e domínio seguido de caminho ou porta sem esquema; o host, como o navegador o lê.
ESQUEMA = re.compile(r"(?<![\w+.$-])([a-z][a-z0-9+.-]+):(?=\S)", re.I)  # $env:VAR é variável do PowerShell
WWW = re.compile(r"(?<![\w.@/\\:-])www\.", re.I)
DOMINIO_COM_CAMINHO = re.compile(r"(?<![\w.@/\\:~%$-])((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63})(?=/|:\d)",
                                 re.I)
AUTORIDADE = re.compile(r"[\\/]*([^\s\\/?#]*)")  # depois do esquema: as barras (\ vale /) e até a barra, ? ou #
# Caracteres que não se veem: de controle (fora a quebra de linha), de formatação, não atribuídos, de uso privado,
# substitutos e separadores de linha e de parágrafo; e os que são letra ou símbolo mas aparecem em branco (R177C-B-05):
# os preenchedores do hangul (U+115F, U+1160, U+3164, U+FFA0), o Braille em branco, o CGJ, as vogais inerentes do
# khmer e os seletores de variação.
CATEGORIAS_INVISIVEIS = frozenset({"Cc", "Cf", "Cn", "Co", "Cs", "Zl", "Zp"})
INVISIVEIS = frozenset(map(chr, (0x034F, 0x115F, 0x1160, 0x17B4, 0x17B5, 0x2800, 0x3164, 0xFFA0)))


def sha256(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def e_ligacao(p: Path) -> bool:
    """Link simbólico ou junção do Windows (a regra do `instalar_skill.py`; `os.path.isjunction` só existe a partir do
    3.12, e no 3.10/3.11 a junção é reconhecida pela marca de ponto de montagem do `lstat`)."""
    if p.is_symlink():
        return True
    is_junction = getattr(os.path, "isjunction", None)
    if is_junction is not None:
        return bool(is_junction(p))
    if os.name != "nt":
        return False
    try:
        st = os.lstat(p)
    except OSError:
        return False
    return bool(getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT) and \
        getattr(st, "st_reparse_tag", None) == stat.IO_REPARSE_TAG_MOUNT_POINT


def versao_de(texto: str) -> str | None:
    m = VERSAO.search(texto)
    return m.group(1) if m else None


def arquivos_da_arvore(skill: Path) -> list[Path]:
    """Arquivos comuns da árvore, sem seguir ligações. Ligação em qualquer ponto (a pasta da skill inclusive) levanta
    ValueError: o zip seguiria a ligação e publicaria o alvo (a regra do empacotar.py; varredura da 1.4.5, #1)."""
    ligacoes = [skill.name] if e_ligacao(skill) else []
    arquivos = []
    for base, pastas, nomes in os.walk(skill):
        ligacoes += [(Path(base) / n).relative_to(skill).as_posix() for n in [*pastas, *nomes]
                     if e_ligacao(Path(base) / n)]
        pastas[:] = [d for d in pastas if not e_ligacao(Path(base) / d)]  # não desce por uma ligação
        arquivos += [Path(base) / n for n in nomes if not e_ligacao(Path(base) / n) and (Path(base) / n).is_file()]
    if ligacoes:
        raise ValueError("ligação (link simbólico ou junção) na árvore da skill: " + ", ".join(sorted(ligacoes)[:10]))
    return sorted(arquivos)


def no_skill(rel: str) -> bool:
    """O package_skill.py leva este arquivo (`rel`: caminho com barras a partir da pasta da skill) para o .skill? Mesma
    regra do `should_exclude` dele, aplicada ao caminho a partir da pasta-mãe da skill."""
    partes = (NOME, *rel.split("/"))
    if any(p in FORA_DO_SKILL_PASTAS for p in partes) or partes[1] in FORA_DO_SKILL_NA_RAIZ:
        return False
    return partes[-1] not in FORA_DO_SKILL_ARQUIVOS and \
        not any(fnmatch.fnmatch(partes[-1], padrao) for padrao in FORA_DO_SKILL_PADROES)


def no_completo(rel: str) -> bool:
    """O empacotar.py leva este arquivo para o completo? Tudo, menos __pycache__ e *.pyc (`arquivos_da_skill` dele)."""
    caminho = PurePosixPath(rel)
    return "__pycache__" not in caminho.parts and caminho.suffix != ".pyc"


def esperados(skill: Path, *, completo: bool) -> dict[str, str]:
    """Membros que o pacote tem de ter, lidos da árvore agora: `fundacao-ia-multiprojetos/<caminho>` -> SHA-256."""
    regra = no_completo if completo else no_skill
    res = {}
    for p in arquivos_da_arvore(skill):
        rel = p.relative_to(skill).as_posix()
        if regra(rel):
            res[f"{NOME}/{rel}"] = sha256(p.read_bytes())
    return res


def nome_ruim(nome: str, pasta: str = NOME) -> str | None:
    """Por que o nome de um membro não serve, ou None: tem de ficar sob a `pasta` (a da skill; no zip de transferência,
    `<nome>-<versão>`), sem componente vazio, `.`, `..`, barra invertida, dois-pontos ou caractere de controle."""
    partes = nome.split("/")
    if partes[0] != pasta or len(partes) < 2:
        return f"fora da pasta {pasta}/"
    if any(p in ("", ".", "..") or any(c in "\\:" or ord(c) < 32 for c in p) for p in partes):
        return "componente vazio, '.', '..', barra invertida, dois-pontos ou controle"
    return None


def fora_das_entradas(dados: bytes, infos: list[zipfile.ZipInfo]) -> str | None:
    """Primeiro trecho do arquivo que não pertence a nenhuma entrada, ou None. O zip que o zipfile grava é canônico:
    entradas coladas desde o byte 0, cada cabeçalho local igual ao do diretório central, o diretório central logo
    depois da última entrada e o registro de fim no fim do arquivo, sem comentário. Assim nenhum leitor de zip vê
    membros diferentes dos conferidos, e nenhum byte fica escondido fora deles."""
    pos = 0
    for i in sorted(infos, key=lambda x: x.header_offset):
        if i.header_offset != pos:
            return f"bytes fora das entradas antes de {i.filename!r}"
        cabecalho = dados[pos:pos + 30]
        if len(cabecalho) < 30 or cabecalho[:4] != b"PK\x03\x04":
            return f"cabeçalho local ausente em {i.filename!r}"
        _v, bits, metodo, _h, _d, crc, comprimido, tamanho, n, m = struct.unpack("<HHHHHIIIHH", cabecalho[4:])
        if (bits, metodo, crc, comprimido, tamanho) != (i.flag_bits, i.compress_type, i.CRC, i.compress_size,
                                                        i.file_size):
            return f"cabeçalho local de {i.filename!r} diferente do diretório central"
        pos += 30 + n + m + i.compress_size
    fim = dados[-22:]
    if len(fim) < 22 or fim[:4] != b"PK\x05\x06":
        return "registro de fim fora do lugar (bytes depois dele ou comentário)"
    _d1, _d2, _n1, total, tamanho_cd, inicio_cd, comentario = struct.unpack("<HHHHIIH", fim[4:])
    if comentario or inicio_cd != pos or inicio_cd + tamanho_cd != len(dados) - 22 or total != len(infos):
        return "diretório central fora do lugar (bytes entre ele e as entradas, depois dele ou comentário)"
    return None


def examinar_zip(rotulo: str, dados: bytes, *, pasta: str = NOME, exigir_skill_md: bool = True,
                 tipo_opcional: bool = False) -> tuple[dict[str, str], str | None, list[str]]:
    """Estrutura de um pacote (os bytes lidos uma vez): devolve os membros (nome -> SHA-256), a versão do SKILL.md de
    dentro e os problemas. Membro com problema de estrutura não é lido. No zip de transferência (`pasta`
    `<nome>-<versão>`, sem SKILL.md), `tipo_opcional` aceita também o modo sem o tipo de arquivo (0o600, o que o
    `writestr` grava): continua recusando pasta, ligação e bits especiais."""
    try:
        z = zipfile.ZipFile(io.BytesIO(dados))
    except (zipfile.BadZipFile, OSError, ValueError) as e:
        return {}, None, [f"{rotulo}: não é um zip válido ({type(e).__name__}: {e})"]
    membros, problemas, vistos = {}, [], set()
    with z:
        infos = z.infolist()
        if len(infos) > LIMITE_ENTRADAS or sum(i.file_size for i in infos) > LIMITE_BYTES:
            return {}, None, [f"{rotulo}: mais de {LIMITE_ENTRADAS} entradas ou de {LIMITE_BYTES // 2**20} MiB"]
        for i in infos:
            modo = i.external_attr >> 16
            motivo = nome_ruim(i.filename, pasta)
            tipo_ok = stat.S_IFMT(modo) == stat.S_IFREG or (tipo_opcional and stat.S_IFMT(modo) == 0)
            if motivo is None and (i.is_dir() or i.external_attr & 0xFFFF or not tipo_ok or modo & 0o7000):
                motivo = f"não é arquivo comum (modo {modo:#o}, atributos {i.external_attr & 0xFFFF:#x})"
            if motivo is None and (i.flag_bits & ~BITS_PERMITIDOS or i.compress_type not in COMPRESSOES):
                motivo = f"cifra, descritor de dados ou compressão {i.compress_type} (bits {i.flag_bits:#x})"
            chave = unicodedata.normalize("NFC", i.filename).casefold()
            if motivo is None and chave in vistos:
                motivo = "nome repetido (também por maiúsculas/minúsculas ou forma Unicode)"
            vistos.add(chave)
            if motivo:
                problemas.append(f"{rotulo}: {i.filename!r} {motivo}")
                continue
            try:
                membros[i.filename] = sha256(z.read(i))  # confere o CRC e o nome do cabeçalho local
            except (zipfile.BadZipFile, zlib.error, EOFError, OSError, RuntimeError, NotImplementedError,
                    ValueError) as e:
                problemas.append(f"{rotulo}: {i.filename!r} ilegível ({type(e).__name__}: {e})")
        fora = fora_das_entradas(dados, infos)
        if fora:
            problemas.append(f"{rotulo}: {fora}")
        versao = None
        if f"{NOME}/SKILL.md" in membros:
            versao = versao_de(z.read(f"{NOME}/SKILL.md").decode("utf-8", "replace"))
        elif exigir_skill_md:
            problemas.append(f"{rotulo}: sem {NOME}/SKILL.md")
    return membros, versao, problemas


def diferencas(rotulo: str, membros: dict[str, str], esperado: dict[str, str], referencia: str) -> list[str]:
    """Membros a mais, a menos e com bytes diferentes de `esperado` (o que `referencia` diz que o pacote tem)."""
    res = [f"{rotulo}: {n} a mais (não está n{referencia})" for n in sorted(set(membros) - set(esperado))]
    res += [f"{rotulo}: {n} a menos (está n{referencia})" for n in sorted(set(esperado) - set(membros))]
    res += [f"{rotulo}: {n} com bytes diferentes d{referencia}" for n in sorted(set(membros) & set(esperado))
            if membros[n] != esperado[n]]
    return res


def conferir_contra_a_arvore(pacote: Path, skill: Path, *, completo: bool) -> list[str]:
    """Problemas do pacote contra a árvore (lista vazia = é a árvore): estrutura e membros, nome a nome, byte a byte.
    É o que o empacotar.py exige de cada pacote gerado antes de gravar o SHA256SUMS.txt."""
    membros, _versao, problemas = examinar_zip(pacote.name, pacote.read_bytes())
    try:
        esperado = esperados(skill, completo=completo)
    except (ValueError, OSError) as e:
        return problemas + [f"{pacote.name}: a árvore não pôde ser lida ({e})"]
    return problemas + diferencas(pacote.name, membros, esperado, "a árvore")


def ler_sums(caminho: Path) -> tuple[dict[str, str], list[str]]:
    """Linhas `<sha256>  <nome>` do SHA256SUMS.txt (nome com ou sem `*`); outra forma ou nome repetido é problema."""
    if not caminho.is_file():
        return {}, [f"{caminho.name} ausente em {caminho.parent}"]
    sums, problemas = {}, []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        partes = linha.split()
        if not partes:
            continue
        if len(partes) != 2 or not re.fullmatch(r"[0-9a-f]{64}", partes[0]) or partes[1].lstrip("*") in sums:
            problemas.append(f"{caminho.name}: linha fora do formato ou repetida: {linha[:120]!r}")
            continue
        sums[partes[1].lstrip("*")] = partes[0]
    return sums, problemas


def linhas_do_historico(texto: str) -> set[str]:
    return {linha.strip() for linha in texto.splitlines() if linha.strip() and not linha.lstrip().startswith("#")}


def ler_historico(caminho: Path) -> tuple[dict[str, str], list[str]]:
    """Lista dos pacotes liberados, `<sha256>  <versão>/<arquivo>` por linha (`#` comenta): devolve
    (`<versão>/<arquivo>` -> sha256, problemas). Linha fora do formato e a mesma chave com outro hash são problema:
    cada pacote liberado tem um só conteúdo, e a lista só cresce (R177-ATU-04)."""
    if e_ligacao(caminho) or not caminho.is_file():
        return {}, [f"{HISTORICO} ausente (ou ligação) em {caminho.parent}"]
    historico, problemas = {}, []
    for linha in sorted(linhas_do_historico(caminho.read_text(encoding="utf-8"))):
        m = LINHA_DO_HISTORICO.fullmatch(linha)
        if m is None:
            problemas.append(f"{HISTORICO}: linha fora do formato: {linha[:120]!r}")
        elif historico.setdefault(m[2], m[1]) != m[1]:
            problemas.append(f"{HISTORICO}: {m[2]} repetido com outro hash: cada pacote liberado tem um só conteúdo")
    return historico, problemas


def conferir_crescimento(lista: Path) -> list[str]:
    """--lista-so-cresce: cada versão de `lista` nos commits do git que a tocaram está contida na atual. Precisa do git
    e da história inteira; sem eles, reprova."""
    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(lista.parent), *args], capture_output=True, timeout=120)
    try:
        raso = git("rev-parse", "--is-shallow-repository")
        if raso.returncode != 0:
            return [f"{HISTORICO}: fora de um repositório git; --lista-so-cresce precisa da história dela"]
        if raso.stdout.decode().strip() == "true":
            return [f"{HISTORICO}: clone raso, sem a história da lista (na CI, fetch-depth: 0)"]
        rel = git("rev-parse", "--show-prefix").stdout.decode("utf-8").strip() + lista.name  # a partir da raiz do git
        atual = linhas_do_historico(lista.read_text(encoding="utf-8"))
        problemas = []
        for commit in git("log", "--format=%H", "--", lista.name).stdout.decode().split():  # caminho da pasta atual
            antiga = git("show", f"{commit}:{rel}")
            faltam = linhas_do_historico(antiga.stdout.decode("utf-8", "replace")) - atual if antiga.returncode == 0 \
                else set()  # o commit que a apagou não tem conteúdo
            if faltam:
                problemas.append(f"{HISTORICO}: a lista só cresce, e {len(faltam)} linha(s) do commit {commit[:12]} "
                                 f"não estão mais nela (ex.: {sorted(faltam)[0][:100]})")
        return problemas
    except (OSError, subprocess.SubprocessError) as e:
        return [f"{HISTORICO}: git indisponível ({type(e).__name__}): --lista-so-cresce precisa dele"]


def conferir_anteriores(pasta: Path, historico: dict[str, str] | None = None) -> tuple[int, list[str]]:
    """Conjuntos guardados em dist/anteriores/: cada pacote listado no SHA256SUMS.txt da pasta, com o mesmo hash, zip
    íntegro, a versão de dentro igual à da pasta (`<versão>` ou `<versão>-<data>`) e, com o `historico`, o mesmo hash
    da lista dos pacotes liberados para `<versão>/<arquivo>` (R177-ATU-04). Devolve (conjuntos, problemas)."""
    if not pasta.is_dir():
        return 0, []
    conjuntos, problemas = 0, []
    for conjunto in sorted(pasta.iterdir()):
        conjuntos += 1
        if e_ligacao(conjunto) or not conjunto.is_dir():
            problemas.append(f"anteriores/{conjunto.name}: não é pasta comum")
            continue
        sums, p = ler_sums(conjunto / "SHA256SUMS.txt")
        problemas += [f"anteriores/{conjunto.name}/{x}" for x in p]
        pacotes = sorted(a.name for a in conjunto.iterdir() if a.suffix in (".skill", ".zip"))
        if not pacotes:
            problemas.append(f"anteriores/{conjunto.name}: sem pacote")
        for nome in sorted(set(sums) | set(pacotes)):
            arquivo, rotulo = conjunto / nome, f"anteriores/{conjunto.name}/{nome}"
            if e_ligacao(arquivo) or not arquivo.is_file() or nome not in sums:
                problemas.append(f"{rotulo}: listado sem arquivo, arquivo sem estar listado ou ligação")
                continue
            dados = arquivo.read_bytes()
            if sha256(dados) != sums[nome]:
                problemas.append(f"{rotulo}: SHA-256 não confere com o SHA256SUMS.txt da pasta")
                continue
            try:
                with zipfile.ZipFile(io.BytesIO(dados)) as z:
                    ruim = z.testzip()
                    versao = versao_de(z.read(f"{NOME}/SKILL.md").decode("utf-8", "replace"))
            except (zipfile.BadZipFile, KeyError, zlib.error, EOFError, OSError, RuntimeError,
                    NotImplementedError, ValueError) as e:
                problemas.append(f"{rotulo}: zip ilegível ({type(e).__name__}: {e})")
                continue
            if ruim:
                problemas.append(f"{rotulo}: membro corrompido {ruim}")
            if versao is None or not (conjunto.name == versao or conjunto.name.startswith(f"{versao}-")):
                problemas.append(f"{rotulo}: versão {versao!r} de dentro não é a da pasta")
            elif historico is not None and historico.get(f"{versao}/{nome}") != sums[nome]:
                problemas.append(f"{rotulo}: não está, com este hash, na lista dos pacotes liberados ({HISTORICO}): "
                                 "conjunto coerente consigo mesmo não basta")
    return conjuntos, problemas


def termo_da_linha(bruto: str) -> tuple[str, bool]:
    """O termo em minúsculas, sem as aspas (também as tipográficas, que o PowerShell aceita), crases e circunflexos que
    o shell tira (`c"u"rl`, `cu^rl` e c`url rodam o curl; R177C-B-05), sem `$(`, `@` e colchetes na frente e sem a
    pontuação da frase no fim, e se um parêntese colado o chama (`iex(...)`)."""
    sem_aspas = re.sub(r"[\"'`^\u2018-\u201f]", "", bruto.lower())
    nome, parentese, _ = re.sub(r"^(?:\$\(|[@(\[{])+", "", sem_aspas).partition("(")
    return nome.rstrip(":;,.!?()[]{}"), bool(parentese)


def host_permitido(host: str) -> bool:
    host = host.lower().rstrip(".")
    return any(host == d or host.endswith("." + d) for d in HOSTS_DO_LEIA_ME)


def caminho(nome: str) -> str | None:
    """Tipo do caminho: "explícito" (CAMINHO_EXPLICITO: roda de qualquer ponto da linha), "implícito" (outro com / ou
    \\: só no lugar de um comando) ou None; pasta (termina na barra), endereço com esquema e data ou versão (21/10/2026,
    3.10/3.11) não são caminho de programa (R177C-B-05)."""
    if not re.search(r"[\\/]", nome) or nome[-1] in "\\/" or ESQUEMA.match(nome) or VERSAO_SOLTA.fullmatch(nome):
        return None
    return "explícito" if CAMINHO_EXPLICITO.match(nome) else "implícito"


def executavel(nome: str) -> bool:
    """Nome com extensão de programa na última parte (EXTENSOES_EXECUTAVEIS), fora o de um host permitido (claude.com,
    anthropic.com) e o de um endereço com esquema (R177C-B-05)."""
    ultima = re.split(r"[\\/]", nome)[-1]
    return "." in ultima and ultima.rpartition(".")[2] in EXTENSOES_EXECUTAVEIS and not host_permitido(nome) and \
        not ESQUEMA.match(nome)


def manda_rodar(linha: str) -> bool:
    """A linha do LEIA-ME manda rodar algo? Começa por operador de shell, ou tem (os operadores ; & && | || separam os
    termos mesmo colados):
    - programa de PROGRAMAS (o nome, ou a última parte do caminho, sem .exe) seguido de parêntese ou de argumento
      (`curl x/y.sh`, `iex(...)`, `powershell -c`); fora os PROGRAMAS_FRACOS, também seguido de qualquer palavra
      (`pip install x`) ou sozinho no lugar de um comando, se a frase não acaba nele (`(PowerShell, nesta pasta)` e
      `Windows (PowerShell):` não; terceira passada, R177C-B-05);
    - caminho explícito ou nome com extensão de programa, em qualquer ponto (`C:\\...\\curl.exe`, `./instalar.sh`,
      `rode ajudante.ps1`; R177C-B-05);
    - outro caminho no lugar de um comando (começo da linha, depois de dois-pontos, como o de um rótulo, ou de um dos
      OPERADORES), se a frase não acaba nele, sozinho ou seguido de palavra que não abre parêntese: `bin/ajudante --x`
      manda rodar, e `~/.claude/skills/<nome> (junção no Windows...)`, no LEIA-ME real, é explicação (R177C-B-05).
    "Python 3.10" e "se o comando python não existir" não."""
    if linha.lstrip()[:1] in tuple("&|;<>`$"):
        return True
    termos = re.sub(r"(&&|\|\||[;&|])", r" \1 ", linha).split()
    no_lugar_de_comando = {0} | {i + 1 for i, t in enumerate(termos) if t in OPERADORES or t.endswith(":")}
    for i, termo in enumerate(termos):
        nome, parentese = termo_da_linha(termo)
        if not nome or ESQUEMA.match(nome):
            continue  # endereço: vale a regra dos endereços
        bruto, fim_de_frase = termos[i + 1] if i + 1 < len(termos) else "", termo[-1] in ",.:!?)"
        tipo, programa = caminho(nome), re.split(r"[\\/]", nome)[-1]
        programa = programa[:-4] if programa.endswith(".exe") else programa
        if tipo == "explícito" or executavel(nome):
            return True
        if programa in PROGRAMAS and programa not in PROGRAMAS_FRACOS and not fim_de_frase and \
                (bruto or i in no_lugar_de_comando):
            return True
        seguinte = bruto.rstrip(".,;:!?)")  # pontuação da frase
        if programa in PROGRAMAS and (parentese or (seguinte and not VERSAO_SOLTA.fullmatch(seguinte) and
                                                    ARGUMENTO.match(seguinte))):
            return True
        if tipo == "implícito" and i in no_lugar_de_comando and not fim_de_frase and not bruto.startswith("("):
            return True
    return False


def host_do_endereco(texto: str, inicio: int) -> str:
    """O host do endereço que começa em `inicio` (depois do esquema e dos dois-pontos, ou no `www.`), como o navegador o
    lê: depois das barras, até a barra, ?, # ou espaço seguinte, sem o usuário (até o último @), a porta e a pontuação
    da frase. Antes da terceira passada (R177C-B-05) o host passava do `#`, do `?` e da barra invertida, e um endereço
    como `https://exemplo#.claude.ai` valia como subdomínio de claude.ai: o navegador vai a exemplo."""
    host = AUTORIDADE.match(texto, inicio)[1].rpartition("@")[2]
    return (host if host.startswith("[") else host.partition(":")[0]).rstrip(".,;:!?)]}>\"'`").lower()


def problemas_de_endereco(rotulo: str, texto: str) -> list[str]:
    """Endereços do LEIA-ME fora de http(s) dos HOSTS_DO_LEIA_ME: outro esquema (ftp:, file:, ms-msdt:...), e www. ou
    domínio com caminho sem esquema para outro host (R177C-B-05)."""
    esquemas, hosts = set(), set()
    for m in ESQUEMA.finditer(texto):
        if m[1].lower() in ("http", "https"):
            hosts.add(host_do_endereco(texto, m.end()))
        else:
            esquemas.add(m[1].lower())
    hosts |= {host_do_endereco(texto, m.start()) for m in WWW.finditer(texto)}
    hosts |= {m[1].lower() for m in DOMINIO_COM_CAMINHO.finditer(texto)}
    permitidos = ", ".join(HOSTS_DO_LEIA_ME)
    problemas = [f"{rotulo}: o LEIA-ME.txt cita endereço {e}:, e só valem http e https de {permitidos}"
                 for e in sorted(esquemas)]
    return problemas + [f"{rotulo}: o LEIA-ME.txt aponta para {h or '(sem host)'}, fora de {permitidos}"
                        for h in sorted(hosts) if not host_permitido(h)]


def invisivel(c: str) -> bool:
    """Caractere que não se vê (CATEGORIAS_INVISIVEIS, INVISIVEIS e seletores de variação); a quebra de linha, não."""
    return c != "\n" and (unicodedata.category(c) in CATEGORIAS_INVISIVEIS or c in INVISIVEIS or
                          "\ufe00" <= c <= "\ufe0f" or "\U000e0100" <= c <= "\U000e01ef")


def conferir_leia_me(rotulo: str, dados: bytes, hash_skill: str) -> list[str]:
    """LEIA-ME da transferência da versão de dist/ (ver --exigir-transferencia no topo): conferência pela forma, não
    pelo conteúdo — o que o prende de fato é a linha na lista (R177B-B-07)."""
    try:
        texto = dados.decode("utf-8")
    except UnicodeDecodeError:
        return [f"{rotulo}: o LEIA-ME.txt não é texto UTF-8"]
    problemas = [f"{rotulo}: o LEIA-ME.txt tem caractere de controle ou invisível (U+{ord(c):04X})" for c in
                 sorted({c for c in texto if invisivel(c)})]
    texto = unicodedata.normalize("NFKC", texto)  # pip em letra larga (U+FF50...) é o pip (R177C-B-05)
    problemas += [f"{rotulo}: o LEIA-ME.txt cita o hash {h[:16]}..., que não é o do {PACOTE} de dist/" for h in
                  sorted(set(re.findall(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{64}(?![0-9A-Fa-f])", texto))) if
                  h.lower() != hash_skill]
    problemas += problemas_de_endereco(rotulo, texto)
    for linha in texto.splitlines():
        if not manda_rodar(linha) or any(p.fullmatch(" ".join(linha.split())) for p in CITACOES_DO_LEIA_ME):
            continue
        rotulo_da_linha = ROTULO_DO_LEIA_ME.match(linha.strip())
        resto = linha.strip()[rotulo_da_linha.end():] if rotulo_da_linha else linha.strip()
        if (rotulo_da_linha and manda_rodar(rotulo_da_linha.group())) or \
                not any(p.fullmatch(" ".join(resto.split())) for p in COMANDOS_DO_LEIA_ME):
            problemas.append(f"{rotulo}: o LEIA-ME.txt manda rodar o que não é o instalador nem a conferência do hash: "
                             f"{linha.strip()[:100]!r}")
    return problemas


def conferir_zip_de_transferencia(rotulo: str, dados: bytes, versao: str, historico: dict, skill: bytes | None,
                                  instalador: Path | None) -> list[str]:
    """Zip principal da transferência (`<nome>-<versão>/` com LEIA-ME.txt, o .skill, o instalar_skill.py e o
    SHA256SUMS.txt): estrutura pelo `examinar_zip`, exatamente esses membros, SHA256SUMS.txt coerente e o .skill igual
    ao de dist/ (versão de dist/, com o instalador igual ao de entrega/) ou ao da lista (versão anterior). E o zip
    inteiro na lista (R177B-B-07): obrigatório na versão anterior; na de dist/, com a linha vale o hash dela, e o
    LEIA-ME passa pelo `conferir_leia_me` com ou sem ela (na CI, a linha pode ter vindo no mesmo commit que o zip;
    terceira passada, R177C-B-05)."""
    pasta = f"{NOME}-{versao}"
    membros, _versao, problemas = examinar_zip(rotulo, dados, pasta=pasta, exigir_skill_md=False, tipo_opcional=True)
    dentro = {n[len(pasta) + 1:]: h for n, h in membros.items()}
    if set(dentro) != set(MEMBROS_DA_TRANSFERENCIA):
        problemas.append(f"{rotulo}: membros {sorted(dentro)}; esperado exatamente {sorted(MEMBROS_DA_TRANSFERENCIA)}")
    if problemas:
        return problemas
    if skill is not None and dentro[PACOTE] != sha256(skill):
        problemas.append(f"{rotulo}: o {PACOTE} de dentro não é o de dist/")
    elif skill is None and historico.get(f"{versao}/{PACOTE}") != dentro[PACOTE]:
        problemas.append(f"{rotulo}: o {PACOTE} de dentro não é o da {versao} na lista dos liberados ({HISTORICO})")
    if instalador is not None:
        esperado = sha256(instalador.read_bytes()) if instalador.is_file() and not e_ligacao(instalador) else None
        if dentro["instalar_skill.py"] != esperado:
            problemas.append(f"{rotulo}: o instalar_skill.py de dentro não é o de entrega/")
    with zipfile.ZipFile(io.BytesIO(dados)) as z:  # já conferido pelo examinar_zip
        sums = z.read(f"{pasta}/SHA256SUMS.txt").decode("utf-8", "replace")
        leia_me = z.read(f"{pasta}/LEIA-ME.txt")
    listados = {p[1].lstrip("*"): p[0] for p in (linha.split() for linha in sums.splitlines()) if len(p) == 2}
    if listados != {PACOTE: dentro[PACOTE], "instalar_skill.py": dentro["instalar_skill.py"]}:
        problemas.append(f"{rotulo}: o SHA256SUMS.txt de dentro não confere com o {PACOTE} e o instalar_skill.py")
    fixado = historico.get(f"{versao}/{pasta}.zip")
    if fixado is not None and fixado != sha256(dados):
        problemas.append(f"{rotulo}: não é, com este hash, o zip da {versao} na lista dos liberados ({HISTORICO}): o "
                         "LEIA-ME e o instalador publicados não mudam")
    elif fixado is None and skill is None:
        problemas.append(f"{rotulo}: zip de versão anterior fora da lista dos liberados ({HISTORICO}); a liberação "
                         "acrescenta a linha dele ao montar a transferência")
    if skill is not None:
        problemas += conferir_leia_me(rotulo, leia_me, sha256(skill))
    return problemas


def conferir_transferencia(pasta: Path, historico: dict, skill: bytes | None, versao: str | None,
                           instalador: Path, exigir_fixada: bool = False) -> tuple[dict, list[str]]:
    """entrega/transferencia/ (ver --exigir-transferencia e --exigir-transferencia-fixada no topo). Devolve (resumo,
    problemas)."""
    if e_ligacao(pasta) or not pasta.is_dir():
        return {}, [f"transferencia/ ausente (ou ligação) em {pasta.parent}: a CI pública exige a da versão de dist/"]
    problemas, vistos, arquivos = [], set(), 0
    for arq in sorted(pasta.iterdir()):
        rotulo, m = f"transferencia/{arq.name}", TRANSFERENCIA.fullmatch(arq.name)
        if m is None or e_ligacao(arq) or not arq.is_file():
            problemas.append(f"{rotulo}: não é arquivo da transferência (<nome>-<versão>.zip, -para-claude-ai.zip ou "
                             "-para-revisao.md) ou é ligação")
            continue
        arquivos += 1
        v = m["versao"]
        if m["revisao"]:
            continue  # texto para revisão por outra IA: não se instala e não é conferido aqui
        dados = arq.read_bytes()
        vistos.add((v, bool(m["claude"])))
        if not m["claude"]:
            problemas += conferir_zip_de_transferencia(rotulo, dados, v, historico, skill if v == versao else None,
                                                       instalador if v == versao else None)
        elif v == versao and skill is not None:
            if dados != skill:
                problemas.append(f"{rotulo}: não é byte a byte o {PACOTE} de dist/ (é ele que vai ao claude.ai)")
        elif historico.get(f"{v}/{PACOTE}") != sha256(dados):
            problemas.append(f"{rotulo}: não é o {PACOTE} da {v} na lista dos liberados ({HISTORICO})")
    for claude, sufixo in ((True, "-para-claude-ai.zip"), (False, ".zip")):
        if versao and (versao, claude) not in vistos:
            problemas.append(f"transferencia/{NOME}-{versao}{sufixo} ausente: é a transferência da versão de dist/")
    for chave in sorted(historico):  # transferência publicada não sai da pasta (terceira passada, R177C-B-05)
        m = re.fullmatch(r"(\d+(?:\.\d+)+)/" + re.escape(NOME) + r"-\1\.zip", chave)
        if m and m[1] != versao and (m[1], False) not in vistos:
            problemas.append(f"transferencia/{NOME}-{m[1]}.zip ausente: está na lista dos liberados ({HISTORICO}), e "
                             "a transferência publicada não sai da pasta")
    fixada = f"{versao}/{NOME}-{versao}.zip" in historico  # sem a linha, só a forma do LEIA-ME o prende (B-07)
    if exigir_fixada and versao and not fixada:
        problemas.append(f"transferencia/{NOME}-{versao}.zip sem a linha dele na lista dos liberados ({HISTORICO}): "
                         "a CI pública a exige (a etapa 03 da liberação a acrescenta depois de conferir o LEIA-ME)")
    return {"versao": versao, "arquivos": arquivos, "fixada_na_lista": fixada}, problemas


def verificar(dist: Path = DIST, skill: Path = SKILL, *, exigir_igual_a_arvore: bool = False,
              exigir_transferencia: bool = False, lista_so_cresce: bool = False,
              exigir_transferencia_fixada: bool = False) -> dict:
    """Confere dist/ (sempre) e compara os pacotes com a árvore (reprova só com `exigir_igual_a_arvore`). A lista dos
    pacotes liberados, a transferência e o instalador ficam em entrega/, a pasta de cima de `dist`.
    `exigir_transferencia_fixada` inclui `exigir_transferencia` (R177C-B-05)."""
    exigir_transferencia = exigir_transferencia or exigir_transferencia_fixada
    problemas, entrega, bytes_do_skill = [], Path(dist).parent, None
    sums, p = ler_sums(dist / "SHA256SUMS.txt")
    problemas += p
    if set(sums) != {PACOTE, COMPLETO}:
        problemas.append(f"SHA256SUMS.txt lista {sorted(sums)}; esperado exatamente {[PACOTE, COMPLETO]}")
    pacotes = {}
    for nome in (PACOTE, COMPLETO):
        caminho = dist / nome
        if e_ligacao(caminho) or not caminho.is_file():
            problemas.append(f"{nome} ausente em {dist} (ou é ligação)")
            continue
        dados = caminho.read_bytes()  # lido uma vez: o hash e a análise usam os mesmos bytes
        bytes_do_skill = dados if nome == PACOTE else bytes_do_skill
        h = sha256(dados)
        if sums.get(nome) != h:
            problemas.append(f"{nome}: SHA-256 {h} não confere com o SHA256SUMS.txt ({sums.get(nome)})")
        membros, versao, p = examinar_zip(nome, dados)
        problemas += p
        pacotes[nome] = {"sha256": h, "arquivos": len(membros), "versao": versao, "membros": membros}
    try:
        emp = json.loads((dist / "EMPACOTAMENTO.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        emp = None
        problemas.append(f"EMPACOTAMENTO.json ilegível ({type(e).__name__}: {e})")
    if isinstance(emp, dict) and len(pacotes) == 2:
        if emp.get("sha256") != {n: pacotes[n]["sha256"] for n in pacotes}:
            problemas.append("EMPACOTAMENTO.json: sha256 diferente dos pacotes")
        if emp.get("arquivos") != {n: pacotes[n]["arquivos"] for n in pacotes}:
            problemas.append("EMPACOTAMENTO.json: contagem de arquivos diferente dos pacotes")
        if not emp.get("versao") or {emp.get("versao")} != {pacotes[n]["versao"] for n in pacotes}:
            problemas.append(f"EMPACOTAMENTO.json: versão {emp.get('versao')!r} diferente da de dentro dos pacotes "
                             f"({sorted({str(pacotes[n]['versao']) for n in pacotes})})")
    if len(pacotes) == 2:
        do_completo = {n: h for n, h in pacotes[COMPLETO]["membros"].items() if no_skill(n[len(NOME) + 1:])}
        problemas += diferencas(PACOTE, pacotes[PACOTE]["membros"], do_completo, "o completo")
    historico, p_lista = ler_historico(entrega / HISTORICO)
    conjuntos, p = conferir_anteriores(dist / "anteriores", historico)
    if conjuntos or exigir_igual_a_arvore or exigir_transferencia or lista_so_cresce:
        problemas += p_lista
    problemas += p
    fonte = comparar_com_a_arvore(pacotes, skill)
    if exigir_igual_a_arvore:
        problemas += fonte["divergencias"]
        problemas += [f"{n}: o pacote de dist/ não está, com este hash, na lista dos liberados ({HISTORICO}); o "
                      "empacotar.py o acrescenta" for n, d in pacotes.items()
                      if historico.get(f"{d['versao']}/{n}") != d["sha256"]]
    transferencia = None
    if exigir_transferencia:
        versao = (pacotes.get(PACOTE) or {}).get("versao")
        transferencia, p = conferir_transferencia(entrega / "transferencia", historico, bytes_do_skill, versao,
                                                  entrega / "instalar_skill.py", exigir_transferencia_fixada)
        problemas += p
    if lista_so_cresce:
        problemas += conferir_crescimento(entrega / HISTORICO)
    res = {"ok": not problemas, "modo": "igual à árvore" if exigir_igual_a_arvore else "desenvolvimento",
           "exige_transferencia": exigir_transferencia, "exige_transferencia_fixada": exigir_transferencia_fixada,
           "lista_so_cresce": lista_so_cresce,
           "dist": str(dist), "skill": str(skill),
           "pacotes": {n: {k: v for k, v in d.items() if k != "membros"} for n, d in pacotes.items()},
           "anteriores": conjuntos, "historico": {"arquivo": str(entrega / HISTORICO), "pacotes": len(historico)},
           "transferencia": transferencia, "fonte": fonte, "problemas": problemas}
    return res


def comparar_com_a_arvore(pacotes: dict, skill: Path) -> dict:
    """Versão e membros dos pacotes contra a árvore. `divergencias` vazia = a árvore é a do pacote."""
    try:
        versao = versao_de((skill / "SKILL.md").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        versao = None
    fonte = {"versao": versao, "divergencias": []}
    versoes = {d["versao"] for d in pacotes.values()}
    if versoes != {versao}:
        fonte["divergencias"].append(f"a árvore está na versão {versao!r} e o pacote na {sorted(map(str, versoes))}")
    for nome, completo in ((PACOTE, False), (COMPLETO, True)):
        if nome not in pacotes:
            continue
        try:
            esperado = esperados(skill, completo=completo)
        except (ValueError, OSError) as e:
            fonte["divergencias"].append(f"a árvore não pôde ser lida ({e})")
            break
        fonte["divergencias"] += diferencas(nome, pacotes[nome]["membros"], esperado, "a árvore")
    fonte["igual_ao_pacote"] = not fonte["divergencias"]
    if fonte["divergencias"]:
        fonte["nota"] = ("a árvore não é a do pacote: normal no preparo de uma versão (o pacote só é gerado na "
                         "liberação); a CI pública e a liberação usam --exigir-igual-a-arvore. Se a árvore mudou e "
                         "continua na versão do pacote, suba a versão antes de empacotar")
    return fonte


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dist", type=Path, default=DIST, help="pasta dos pacotes (padrão: entrega/dist)")
    ap.add_argument("--skill", type=Path, default=SKILL, help="pasta da skill (padrão: fundacao-ia-multiprojetos)")
    ap.add_argument("--exigir-igual-a-arvore", action="store_true",
                    help="a árvore tem de ser a do pacote: mesma versão e os mesmos arquivos (CI pública e liberação)")
    ap.add_argument("--exigir-transferencia", action="store_true",
                    help="confere entrega/transferencia/ (a CI pública e a etapa 03 da liberação; ver no topo)")
    ap.add_argument("--lista-so-cresce", action="store_true",
                    help=f"confere pelo git que a {HISTORICO} só cresceu (só a CI pública, com fetch-depth 0)")
    ap.add_argument("--exigir-transferencia-fixada", action="store_true",
                    help="--exigir-transferencia e a linha do zip da versão de dist/ na lista (só a CI pública)")
    a = ap.parse_args(argv)
    res = verificar(a.dist, a.skill, exigir_igual_a_arvore=a.exigir_igual_a_arvore,
                    exigir_transferencia=a.exigir_transferencia, lista_so_cresce=a.lista_so_cresce,
                    exigir_transferencia_fixada=a.exigir_transferencia_fixada)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
