#!/usr/bin/env python3
"""Instala, atualiza, verifica ou remove a skill fundacao-ia-multiprojetos neste computador.

Convenção (a mesma já usada pelas outras skills deste perfil):
  cópia física   ~/.agents/skills/fundacao-ia-multiprojetos        (Codex e outros hosts Agent Skills)
  ligação        ~/.claude/skills/fundacao-ia-multiprojetos  ->  cópia física
                 (Windows: junção de diretório, sem exigir administrador; Linux/macOS: link simbólico)

  python instalar_skill.py instalar   --origem <pacote.skill> --sha256 <hash>
  python instalar_skill.py atualizar  --origem <pacote.skill> --sha256 <hash>
                                          (guarda a anterior em ~/.agents/skills-anteriores/)
  python instalar_skill.py verificar [--origem <pacote | pasta>] [--sha256 <hash>]
                                          (ligação; com --origem, compara os hashes)
  python instalar_skill.py remover                        (pede --confirmar; remove a ligação, a cópia e a
                                                           instalação manual desta skill em ~/.claude/skills)
  Só em desenvolvimento (INSEGURO, desligado por padrão):
  python instalar_skill.py instalar|atualizar --origem <pasta-da-skill> --pasta-de-desenvolvimento-nao-verificada

Somente arquivos locais; nada é baixado. Saída em JSON, também nos erros.
Requer Python 3.10 ou posterior, conferido ANTES de qualquer alteração. A junção do Windows é
reconhecida também sem `os.path.isjunction` (que só existe a partir do 3.12), pela marca de ponto
de montagem do `lstat` — assim verificar, atualizar e remover funcionam no 3.10/3.11.

Origem autenticada (varredura da 1.4.5, #2): `instalar` e `atualizar` exigem `--sha256` com o hash do pacote
recebido por OUTRO canal (quem publicou a versão; numa liberação, o pipeline que acabou de gerar o pacote e
conhece o hash dele). O `SHA256SUMS.txt` ao lado do pacote viaja no mesmo canal: continua conferido e uma
divergência recusa (pega corrupção), mas ele não substitui o `--sha256` nem conta como verificação
(`integridade_do_pacote.ok` só é true com o `--sha256`). Pasta como origem não tem hash: só com
`--pasta-de-desenvolvimento-nao-verificada`, desligada por padrão, e a saída avisa que a origem NÃO foi verificada.
`verificar` não altera nada e não exige `--sha256`; sem ele, diz que o pacote não foi autenticado.

O pacote é lido UMA vez (até 100 MiB) e o hash e a extração usam esses mesmos bytes, em memória: trocar o arquivo
depois da conferência não muda o que se instala (#3). Antes de extrair, as entradas de
`fundacao-ia-multiprojetos/` são conferidas, e qualquer problema recusa o pacote sem alterar nada (auditoria
sobre a 1.4.1, A02): mais de 10.000 entradas ou de 100 MiB descompactados; componente vazio, `.` ou `..`; nome que
o Windows apelida ou descarta (`<>:"|?*`, barra invertida, controle, ponto ou espaço no fim, `CON`, `NUL`,
`COM1`…), recusado em qualquer sistema; link simbólico; duplicata, também por maiúsculas/minúsculas ou forma
Unicode; o mesmo caminho como arquivo e como pasta. Entradas fora dessa pasta não são extraídas. Pasta de origem
com ligação (link simbólico ou junção) é recusada: a cópia a seguiria e traria conteúdo de fora da origem (A02).

Instalar e atualizar trocam a versão por renomeação: a versão nova é copiada para uma área de preparo
FORA das pastas de skills (~/.agents/skills-preparo/), conferida contra o pacote e só então posta no
lugar — a anterior vai para ~/.agents/skills-anteriores/ e a preparada entra no lugar dela (DUAS
renomeações, com uma marca de troca entre elas). Uma falha antes disso não altera nada; uma exceção na
troca ou na ligação devolve a versão anterior e descarta a cópia preparada; se o processo cair entre as
duas renomeações, o próximo `instalar` ou `atualizar` conclui a troca com a cópia preparada (já
conferida), e o `verificar` avisa enquanto isso não acontecer (auditoria final da 1.4.2, AF-02); se a
marca da troca estiver ilegível, as cópias preparadas que sobrarem em skills-preparo são removidas e
relatadas em `passos`, em vez de ficarem órfãs (conferência da 1.4.3, CF-04). Se o RETORNO à versão anterior
também falhar, a recusa diz isso e onde ela ficou (`versao_anterior_em`), em vez de dizer que ela voltou (A01).
Ligação em conflito é recusada antes de copiar. A origem precisa declarar `name: fundacao-ia-multiprojetos`
no SKILL.md (AF-03; UTF-8 com BOM aceito, e a recusa diz quando não há `name` legível, CF-03); `atualizar`
recusa uma pasta física em ~/.agents/skills que não declare esse `name` (A02).

`remover` relata cada caminho e sai com código 1 se algo ficar no lugar; arquivo somente leitura
não o interrompe; a área de preparo (sobras) também é removida; uma ligação em ~/.claude/skills com o
nome desta skill que aponte para a pasta de OUTRA skill é mantida e relatada (AF-04), mas se o alvo
não existir mais (ligação pendurada) só a ligação é removida e relatada (CF-02); pasta física em
~/.agents/skills ou em ~/.claude/skills que não declare `name: fundacao-ia-multiprojetos` é mantida e
relatada (A02). `verificar` informa se o SQLite tem o FTS5 com o tokenizador do kit da fundação: é só
informativo e não entra em `ok` (a skill instalada não depende dele; o kit, sim).
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata
import zipfile
import zlib
from pathlib import Path

NOME = "fundacao-ia-multiprojetos"
AGENTS = Path.home() / ".agents" / "skills" / NOME
CLAUDE = Path.home() / ".claude" / "skills" / NOME
ANTERIORES = Path.home() / ".agents" / "skills-anteriores"  # versões substituídas por atualizar
PREPARO = Path.home() / ".agents" / "skills-preparo"  # cópia nova em preparo: fora das pastas que os hosts leem
TROCA = PREPARO / "troca-em-andamento.json"  # marca gravada entre as duas renomeações da troca (AF-02)
PADROES_IGNORADOS = ("__pycache__", "*.pyc", "evals")
IGNORAR = shutil.ignore_patterns(*PADROES_IGNORADOS)
OPCAO_PASTA_DEV = "--pasta-de-desenvolvimento-nao-verificada"  # origem sem hash: só desenvolvimento (#2)
LIMITE_BYTES = 100 * 1024 * 1024  # do arquivo do pacote e da soma descompactada declarada (A02)
LIMITE_ENTRADAS = 10_000
RESERVADOS_WINDOWS = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | \
    {f"{prefixo}{n}" for prefixo in ("COM", "LPT") for n in "123456789\u00b9\u00b2\u00b3"}


class Recusa(Exception):
    """Falha relatada em JSON (`erro` e detalhes), com código de saída 1."""

    def __init__(self, erro: str, **detalhes):
        super().__init__(erro)
        self.dados = {"erro": erro, **detalhes}


def hashes(raiz: Path) -> dict[str, str]:
    """Hashes da cópia instalada: tudo, menos `__pycache__` (arquivo estranho na cópia aparece como divergência)."""
    return {p.relative_to(raiz).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(raiz.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def referencia_de(pasta: Path) -> dict[str, str]:
    """Hashes do pacote com os mesmos filtros da cópia (IGNORAR vale para qualquer nível)."""
    return {p.relative_to(pasta).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(pasta.rglob("*"))
            if p.is_file() and not any(fnmatch.fnmatch(parte, padrao) for parte in p.relative_to(pasta).parts
                                       for padrao in PADROES_IGNORADOS)}


def ler_pacote(origem: Path) -> bytes:
    """Lê o pacote UMA vez, até LIMITE_BYTES. O hash e a extração usam estes mesmos bytes: trocar o arquivo
    depois da conferência não muda o que se instala (varredura da 1.4.5, #3)."""
    with open(origem, "rb") as f:
        dados = f.read(LIMITE_BYTES + 1)
    if len(dados) > LIMITE_BYTES:
        raise Recusa(f"o pacote passa de {LIMITE_BYTES // 2**20} MiB; nada foi alterado")
    return dados


def sha_informado(texto: str | None) -> str | None:
    """`--sha256` em minúsculas e sem espaços nas pontas, ou None se não foi informado."""
    if texto is None:
        return None
    sha = texto.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise Recusa("--sha256 precisa dos 64 caracteres hexadecimais de um SHA-256; nada foi alterado")
    return sha


def integridade_do_pacote(origem: Path, dados: bytes, sha: str | None) -> dict:
    """Confere o hash dos bytes lidos ANTES de extrair. Só o `--sha256` (recebido por outro canal) autentica o
    pacote; o SHA256SUMS.txt ao lado, se listar o arquivo, viaja no mesmo canal e só pega corrupção (#2).
    Divergência com qualquer um dos dois recusa a operação; nada é alterado."""
    atual = hashlib.sha256(dados).hexdigest()
    res = {"sha256": atual, "conferido_com": [], "ok": None, "autenticado_por": None}
    esperados = [("--sha256", sha)] if sha else []
    manifesto = origem.parent / "SHA256SUMS.txt"
    if manifesto.is_file():
        listado = None
        for linha in manifesto.read_text(encoding="utf-8", errors="replace").splitlines():
            partes = linha.split()
            if len(partes) == 2 and partes[1].lstrip("*") == origem.name:
                listado = partes[0].lower()
        if listado is None:
            res["nota"] = f"o SHA256SUMS.txt ao lado não lista {origem.name}"
        else:
            esperados.append(("SHA256SUMS.txt", listado))
    for fonte, esperado in esperados:
        res["conferido_com"].append(fonte)
        if atual != esperado:
            raise Recusa(f"o pacote não confere com {fonte}; nada foi alterado",
                         integridade_do_pacote={**res, "ok": False, "esperado": esperado, "fonte": fonte})
    if sha:
        res.update(ok=True, autenticado_por="--sha256")
    else:
        res["nota"] = "; ".join(filter(None, [res.get("nota"), (
            "sem --sha256: pacote NÃO autenticado (o SHA256SUMS.txt ao lado viaja no mesmo canal do pacote e "
            "só detecta corrupção)")]))
    return res


def problema_no_nome(parte: str) -> str | None:
    """Por que um componente de caminho do pacote é ambíguo ou não portável, ou None. Vale em qualquer sistema:
    no Windows o zipfile troca `<>:"|?*` por `_` e tira ponto e espaço do fim (`a?.py` vira `a_.py`, `nota.md.`
    vira `nota.md`), e um nome de dispositivo (`nul`, `CON.txt`) não vira arquivo (auditoria sobre a 1.4.1, A02)."""
    if parte in ("", ".", ".."):
        return "componente vazio, '.' ou '..'"
    if any(c in '<>:"|?*\\' or ord(c) < 32 for c in parte):
        return "caractere que o Windows não aceita em nome de arquivo"
    if parte[-1] in ". ":
        return "nome terminado em ponto ou espaço"
    if parte.partition(".")[0].rstrip(" ").upper() in RESERVADOS_WINDOWS:
        return "nome de dispositivo do Windows"
    return None


def membros_conferidos(z: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    """Entradas de `NOME/` a extrair, conferidas ANTES de extrair (auditoria sobre a 1.4.1, A02): limites de
    entradas e de tamanho descompactado declarado, nomes ambíguos ou não portáveis, link simbólico, duplicata
    (também por maiúsculas/minúsculas ou forma Unicode) e o mesmo caminho como arquivo e como pasta. Entradas
    fora de `NOME/` não são extraídas: não seriam instaladas."""
    infos = z.infolist()
    if len(infos) > LIMITE_ENTRADAS or sum(i.file_size for i in infos) > LIMITE_BYTES:
        raise Recusa(f"o pacote passa de {LIMITE_ENTRADAS} entradas ou de {LIMITE_BYTES // 2**20} MiB "
                     "descompactados; nada foi alterado")
    membros, arquivos, pastas = [], set(), set()
    for info in infos:
        partes = info.filename.rstrip("/").split("/")
        if partes[0] != NOME:
            continue
        motivo = next(filter(None, map(problema_no_nome, partes[1:])), None)
        if motivo is None and stat.S_ISLNK(info.external_attr >> 16):
            motivo = "link simbólico"
        if motivo is None and len(partes) == 1 and not info.is_dir():
            motivo = f"{NOME} precisa ser pasta"
        if motivo:
            raise Recusa(f"pacote com entrada recusada ({motivo}): {info.filename!r}; nada foi alterado")
        chaves = [unicodedata.normalize("NFC", "/".join(partes[:i])).casefold() for i in range(1, len(partes) + 1)]
        pastas.update(chaves[:-1])
        if info.is_dir():
            pastas.add(chaves[-1])
        elif chaves[-1] in arquivos:
            raise Recusa("pacote com entrada duplicada (também por maiúsculas/minúsculas ou forma Unicode): "
                         f"{info.filename!r}; nada foi alterado")
        else:
            arquivos.add(chaves[-1])
        membros.append(info)
    if arquivos & pastas:
        raise Recusa(f"pacote com o mesmo caminho como arquivo e como pasta: {min(arquivos & pastas)!r}; "
                     "nada foi alterado")
    return membros


def ligacoes_na_origem(pasta: Path) -> list[str]:
    """Ligações (link simbólico ou junção) na pasta de origem, fora do que a cópia ignora: a cópia as seguiria e
    traria para a instalação conteúdo de fora da origem (auditoria sobre a 1.4.1, A02)."""
    def ignorado(nome: str) -> bool:
        return any(fnmatch.fnmatch(nome, padrao) for padrao in PADROES_IGNORADOS)
    achadas = []
    for base, pastas, arquivos in os.walk(pasta):
        pastas[:] = [d for d in pastas if not ignorado(d)]
        achadas += [(Path(base) / n).relative_to(pasta).as_posix() for n in [*pastas, *arquivos]
                    if not ignorado(n) and e_ligacao(Path(base) / n)]
        pastas[:] = [d for d in pastas if not e_ligacao(Path(base) / d)]  # não desce por uma ligação
    return sorted(achadas)


def origem_como_pasta(origem: Path, tmp: Path, dados: bytes | None = None) -> Path:
    """Pasta com a skill a instalar. Pacote: extrai em `tmp` só as entradas conferidas, a partir de `dados` (os
    mesmos bytes do hash; sem eles, lê o arquivo uma vez aqui). Pasta: recusa ligação dentro dela (A02)."""
    if origem.is_dir():
        if not (origem / "SKILL.md").exists():
            raise Recusa(f"{origem} não contém SKILL.md; nada foi alterado")
        ligacoes = ligacoes_na_origem(origem)
        if ligacoes:
            raise Recusa("a origem contém ligação (link simbólico ou junção), que a cópia seguiria para fora "
                         "dela; use uma cópia física autocontida; nada foi alterado", ligacoes=ligacoes[:20])
        pasta = origem
    else:
        if dados is None:
            dados = ler_pacote(origem)
        try:
            with zipfile.ZipFile(io.BytesIO(dados)) as z:
                z.extractall(tmp, members=membros_conferidos(z))
        except (zipfile.BadZipFile, zlib.error, EOFError, OSError, RuntimeError, NotImplementedError,
                ValueError) as e:
            raise Recusa(f"pacote ilegível ou corrompido ({type(e).__name__}: {e}); nada foi alterado") from e
        pasta = tmp / NOME
        if not (pasta / "SKILL.md").exists():
            raise Recusa(f"pacote sem a pasta {NOME}/SKILL.md na raiz; nada foi alterado")
    declarado = nome_declarado(pasta)
    if declarado is None:
        raise Recusa(f"o SKILL.md da origem não tem um `name` legível no cabeçalho (esperado name: {NOME}); "
                     "nada foi alterado", name_declarado=None)
    if declarado != NOME:
        # A pasta instalada tem nome fixo: o host leria aqui uma skill de outro nome (AF-03).
        raise Recusa(f"o SKILL.md da origem declara name {declarado!r}, não {NOME!r}; nada foi alterado",
                     name_declarado=declarado)
    return pasta


def e_ligacao(p: Path) -> bool:
    """Link simbólico ou junção do Windows. `os.path.isjunction` só existe a partir do Python 3.12;
    no 3.10/3.11 a junção é reconhecida pela marca de ponto de montagem do `lstat` (F17)."""
    if p.is_symlink():
        return True
    is_junction = getattr(os.path, "isjunction", None)  # Python 3.12+
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


BARRA = chr(92)
PREFIXO_LONGO = BARRA * 2 + "?" + BARRA  # caminho estendido do Windows, como o os.readlink devolve o alvo da junção
PREFIXO_UNC_LONGO = PREFIXO_LONGO + "UNC" + BARRA


def alvo_da_ligacao(p: Path) -> Path | None:
    """Alvo gravado na ligação (link simbólico ou junção), absoluto e sem o prefixo estendido; None se ilegível."""
    try:
        alvo = os.readlink(p)
    except (OSError, ValueError):
        return None
    if alvo.startswith(PREFIXO_UNC_LONGO):
        alvo = BARRA * 2 + alvo[len(PREFIXO_UNC_LONGO):]
    elif alvo.startswith(PREFIXO_LONGO):
        alvo = alvo[len(PREFIXO_LONGO):]
    caminho = Path(alvo)
    return caminho if caminho.is_absolute() else p.parent / caminho


def ligacao_aponta_para_copia() -> bool:
    """Compara caminhos finais dos dois lados: a parte que existe sai sem nome curto (8.3) nem ligação no meio. Com a
    cópia ausente (ligação pendurada depois de uma troca interrompida), `CLAUDE.resolve()` devolve o alvo como foi
    gravado, e o perfil com nome curto (CI pública da 1.7.2, RUNNER~1) parecia apontar para outro lugar."""
    if not e_ligacao(CLAUDE):
        return False
    alvo = alvo_da_ligacao(CLAUDE)
    return alvo is not None and Path(os.path.realpath(alvo)) == AGENTS.resolve()


def conferir_ligacao_antes() -> None:
    """Ligação em conflito é recusada ANTES de copiar qualquer coisa."""
    if (CLAUDE.exists() or e_ligacao(CLAUDE)) and not ligacao_aponta_para_copia():
        raise Recusa(f"{CLAUDE} já existe e não é a ligação para {AGENTS}; nada foi alterado. Se for uma "
                     "instalação manual desta skill, `remover --confirmar` a retira; senão, resolva manualmente")


def ligar() -> str:
    CLAUDE.parent.mkdir(parents=True, exist_ok=True)
    if CLAUDE.exists() or e_ligacao(CLAUDE):
        if ligacao_aponta_para_copia():
            return "ligacao-ja-existia"
        raise Recusa(f"{CLAUDE} já existe e não aponta para {AGENTS}; resolva manualmente")
    if os.name == "nt":
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(CLAUDE), str(AGENTS)], capture_output=True, text=True,
                           errors="replace")  # mensagem do cmd vem na página de código do console
        if r.returncode != 0:
            raise Recusa(f"falha ao criar junção: {r.stdout} {r.stderr}")
        return "juncao-criada"
    CLAUDE.symlink_to(AGENTS, target_is_directory=True)
    return "link-simbolico-criado"


def fts5_do_kit() -> bool:
    """O kit da fundação cria as tabelas FTS5 com este tokenizador (SQLite 3.27+); o mesmo teste do
    `scripts/inspecionar_ambiente.py`. Só informativo: não entra em `ok`."""
    con = sqlite3.connect(":memory:")
    try:
        con.execute("CREATE VIRTUAL TABLE t USING fts5(x, tokenize='unicode61 remove_diacritics 2')")
        return True
    except sqlite3.Error:
        return False
    finally:
        con.close()


def verificar(referencia: dict[str, str] | None = None) -> dict:
    res = {"copia": str(AGENTS), "copia_existe": (AGENTS / "SKILL.md").exists(),
           "ligacao": str(CLAUDE), "ligacao_ok": ligacao_aponta_para_copia(),
           "skill_md_legivel_pela_ligacao": (CLAUDE / "SKILL.md").exists()}
    if referencia is not None and res["copia_existe"]:
        b = hashes(AGENTS)
        res["arquivos"] = len(b)
        res["divergentes"] = sorted(k for k in set(referencia) | set(b) if referencia.get(k) != b.get(k))
    if TROCA.is_file():
        # Queda entre as duas renomeações da última troca: só instalar/atualizar concluem (AF-02).
        res["troca_interrompida"] = {"marca": str(TROCA),
                                     "acao": "rode `instalar` ou `atualizar` para concluir a troca com a cópia preparada"}
    res["ok"] = all(res[k] for k in ("copia_existe", "ligacao_ok", "skill_md_legivel_pela_ligacao")) and \
        not res.get("divergentes") and not TROCA.is_file()
    res["informativo"] = {"sqlite": sqlite3.sqlite_version, "fts5_unicode61_remove_diacritics_2": fts5_do_kit(),
                          "nota": "o kit da fundação precisa desse FTS5; não entra em ok"}
    return res


def nome_declarado(pasta: Path) -> str | None:
    """`name` do cabeçalho do SKILL.md da pasta, ou None se não houver um legível. UTF-8 com BOM (arquivo
    editado no Bloco de Notas) é aceito: `utf-8-sig` descarta a marca (conferência da 1.4.3, CF-03)."""
    try:
        linhas = (pasta / "SKILL.md").read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    if not linhas or linhas[0].strip() != "---":
        return None
    for linha in linhas[1:]:
        if linha.strip() == "---":
            break
        if linha.startswith("name:"):
            return linha.split(":", 1)[1].strip().strip("\"'")
    return None


def apagar_arvore(pasta: Path) -> None:
    """`shutil.rmtree` que limpa o atributo somente leitura e tenta de novo; qualquer outra falha, ou a
    mesma se persistir, sobe para quem chamou (nada é engolido)."""
    def tornar_gravavel(func, caminho, erro):
        erro = erro[1] if isinstance(erro, tuple) else erro  # onerror passa exc_info; onexc, a exceção
        if not isinstance(erro, PermissionError):
            raise erro
        os.chmod(caminho, stat.S_IWRITE)
        func(caminho)
    if sys.version_info >= (3, 12):
        shutil.rmtree(pasta, onexc=tornar_gravavel)
    else:
        shutil.rmtree(pasta, onerror=tornar_gravavel)  # `onexc` só existe a partir do 3.12


def caminho_livre(base: Path) -> Path:
    """`base`, ou `base-2`, `base-3`… se já existir (duas operações no mesmo segundo)."""
    candidato, n = base, 2
    while os.path.lexists(candidato):
        candidato, n = base.with_name(f"{base.name}-{n}"), n + 1
    return candidato


def preparar_copia(pasta: Path, referencia: dict[str, str]) -> Path:
    """Copia a versão nova para a área de preparo e confere os hashes; falha não deixa nada para trás."""
    PREPARO.mkdir(parents=True, exist_ok=True)
    destino = caminho_livre(PREPARO / f"{NOME}-{time.strftime('%Y%m%d-%H%M%S')}")
    try:
        shutil.copytree(pasta, destino, ignore=IGNORAR)
        copia = hashes(destino)
        divergentes = sorted(k for k in set(referencia) | set(copia) if referencia.get(k) != copia.get(k))
        if divergentes:
            raise Recusa("a cópia preparada diverge do pacote; nada foi alterado", divergentes=divergentes)
        return destino
    except BaseException:
        shutil.rmtree(destino, ignore_errors=True)
        limpar_preparo()
        raise


def limpar_preparo() -> None:
    try:
        PREPARO.rmdir()  # só se estiver vazia
    except OSError:
        pass


def promover(preparo: Path) -> Path | None:
    """Põe a cópia preparada no lugar por renomeação (mesmo volume). Devolve onde ficou a anterior.

    São DUAS renomeações (anterior -> skills-anteriores; preparo -> skills). Entre elas fica a marca
    `TROCA`: se o processo cair aí, `concluir_troca_interrompida` termina a troca no próximo comando.
    Uma exceção na segunda renomeação devolve a anterior e descarta a cópia preparada (AF-02); se a devolução
    também falhar, a marca e a cópia preparada ficam e a recusa diz onde está a anterior (A01)."""
    anterior = None
    if AGENTS.exists() or e_ligacao(AGENTS):
        ANTERIORES.mkdir(parents=True, exist_ok=True)
        # Fora da pasta de skills: lá, a cópia anterior (mesmo name no SKILL.md) seria lida como outra skill.
        anterior = caminho_livre(ANTERIORES / f"{NOME}-{time.strftime('%Y%m%d-%H%M%S')}")
    TROCA.write_text(json.dumps({"preparo": str(preparo), "anterior": str(anterior) if anterior else None,
                                 "destino": str(AGENTS), "inicio": time.strftime("%Y-%m-%dT%H:%M:%S")},
                                ensure_ascii=False), encoding="utf-8")
    try:
        if anterior is not None:
            os.replace(AGENTS, anterior)
        AGENTS.parent.mkdir(parents=True, exist_ok=True)
        os.replace(preparo, AGENTS)
    except BaseException as erro:
        if anterior is not None and not os.path.lexists(AGENTS):
            try:
                os.replace(anterior, AGENTS)  # devolve a anterior ao lugar
            except OSError as falha:
                raise Recusa("a troca falhou e a versão anterior NÃO voltou ao lugar; nada foi apagado. Rode "
                             "`atualizar` de novo para concluir a troca com a cópia preparada (já conferida), ou "
                             f"devolva a anterior à mão para {AGENTS}",
                             versao_anterior_em=str(anterior), copia_preparada_em=str(preparo),
                             causa=f"{type(erro).__name__}: {erro}",
                             erro_do_retorno=f"{type(falha).__name__}: {falha}") from erro
        shutil.rmtree(preparo, ignore_errors=True)  # a cópia preparada não fica para trás
        TROCA.unlink(missing_ok=True)
        limpar_preparo()
        raise
    TROCA.unlink(missing_ok=True)
    return anterior


def concluir_troca_interrompida() -> dict | None:
    """Queda do processo entre as duas renomeações da troca anterior: conclui a troca com a cópia
    preparada (já conferida contra o pacote) ou, sem ela, devolve a anterior. Devolve o que fez.

    Marca ilegível (JSON inválido ou sem `preparo`): a cópia preparada não pode ser identificada; as pastas
    `<nome>-*` que sobrarem em skills-preparo — nenhum host as lê — são removidas e relatadas, em vez de
    ficarem órfãs até um `remover` (conferência da 1.4.3, CF-04)."""
    if not TROCA.is_file():
        return None
    try:
        marca = json.loads(TROCA.read_text(encoding="utf-8"))
        if not isinstance(marca, dict):
            raise ValueError("marca não é objeto")
    except (OSError, ValueError):
        marca = {}
    legivel = bool(marca.get("preparo"))
    preparo = Path(marca["preparo"]) if legivel else None
    anterior = Path(marca["anterior"]) if marca.get("anterior") else None
    if not os.path.lexists(AGENTS) and preparo is not None and preparo.is_dir():
        AGENTS.parent.mkdir(parents=True, exist_ok=True)
        os.replace(preparo, AGENTS)
        acao = "troca concluída com a cópia preparada"
    elif os.path.lexists(AGENTS):
        acao = "a cópia instalada já estava no lugar"
        if preparo is not None and preparo.is_dir():
            shutil.rmtree(preparo, ignore_errors=True)
            acao += "; cópia preparada descartada"
    elif anterior is not None and anterior.is_dir():
        os.replace(anterior, AGENTS)
        acao = "cópia preparada ausente: versão anterior devolvida ao lugar"
    else:
        acao = "nada a recuperar (sem cópia preparada nem anterior)"
    orfas, nao_removidas = [], []
    if not legivel:
        acao = f"marca de troca ilegível; {acao}"
        for sobra in sorted(PREPARO.glob(f"{NOME}-*")):
            if not sobra.is_dir() or e_ligacao(sobra):
                continue
            try:
                apagar_arvore(sobra)
                orfas.append(sobra.name)
            except OSError as e:
                nao_removidas.append(f"{sobra.name}: {type(e).__name__}: {e}")
    TROCA.unlink(missing_ok=True)
    limpar_preparo()
    return {"marca": marca, "acao": acao, "orfas_removidas": orfas, "orfas_nao_removidas": nao_removidas}


def desfazer(anterior: Path | None, causa: BaseException) -> None:
    """Depois de promover: retira a versão nova e, se havia uma anterior, devolve-a ao lugar. Se esse retorno
    falhar, a recusa diz onde ficaram a anterior e a nova, em vez de dizer que a anterior voltou (A01)."""
    descarte = caminho_livre(PREPARO / f"{NOME}-descartada")
    try:
        PREPARO.mkdir(parents=True, exist_ok=True)
        if os.path.lexists(AGENTS):
            os.replace(AGENTS, descarte)
        if anterior is not None:
            os.replace(anterior, AGENTS)
    except OSError as falha:
        raise Recusa(("a ligação falhou e o retorno à versão anterior também: ela NÃO voltou ao lugar; nada foi "
                      f"apagado. Devolva-a à mão para {AGENTS}") if anterior else
                     f"a ligação falhou e a cópia nova não pôde ser retirada de {AGENTS}; retire-a à mão",
                     versao_anterior_em=str(anterior) if anterior else None,
                     versao_nova_em=str(descarte if os.path.lexists(descarte) else AGENTS),
                     causa=f"{type(causa).__name__}: {causa}",
                     erro_do_retorno=f"{type(falha).__name__}: {falha}") from causa
    shutil.rmtree(descarte, ignore_errors=True)
    limpar_preparo()


def planejar_remocao() -> list[dict]:
    """O que `remover` faz com cada caminho; a mesma lista serve à prévia e à execução."""
    plano = []
    if e_ligacao(CLAUDE):
        alvo = os.path.realpath(CLAUDE)
        if os.path.normcase(alvo) == os.path.normcase(str(AGENTS)) or nome_declarado(Path(alvo)) == NOME:
            plano.append({"caminho": str(CLAUDE), "acao": "remover", "tipo": "ligação", "aponta_para": alvo})
        elif not os.path.lexists(alvo):
            # Ligação pendurada: o alvo não existe mais. Não é skill de ninguém e pode atrapalhar o host; só a
            # ligação é removida, nunca um alvo (conferência da 1.4.3, CF-02).
            plano.append({"caminho": str(CLAUDE), "acao": "remover", "tipo": "ligação", "aponta_para": alvo,
                          "motivo": "ligação pendurada: o alvo não existe mais; só a ligação é removida"})
        else:
            # Ligação com o nome desta skill, mas para a pasta de outra: não foi este instalador que a criou (AF-04).
            plano.append({"caminho": str(CLAUDE), "acao": "manter", "tipo": "ligação", "aponta_para": alvo,
                          "motivo": "aponta para uma pasta que não é desta skill; resolva manualmente"})
    elif CLAUDE.is_dir():
        if nome_declarado(CLAUDE) == NOME:
            plano.append({"caminho": str(CLAUDE), "acao": "remover", "tipo": "pasta desta skill (instalação manual)"})
        else:
            plano.append({"caminho": str(CLAUDE), "acao": "manter", "tipo": "pasta",
                          "motivo": f"o SKILL.md dela não declara name: {NOME}"})
    elif CLAUDE.exists():
        plano.append({"caminho": str(CLAUDE), "acao": "manter", "tipo": "arquivo",
                      "motivo": "não é ligação nem pasta desta skill"})
    if e_ligacao(AGENTS):
        plano.append({"caminho": str(AGENTS), "acao": "remover", "tipo": "ligação",
                      "aponta_para": os.path.realpath(AGENTS)})
    elif AGENTS.is_dir() and nome_declarado(AGENTS) == NOME:
        plano.append({"caminho": str(AGENTS), "acao": "remover", "tipo": "cópia"})
    elif AGENTS.exists():
        # Pasta (ou arquivo) que não declara esta skill: a mesma conferência de ~/.claude/skills (A02).
        plano.append({"caminho": str(AGENTS), "acao": "manter", "tipo": "pasta" if AGENTS.is_dir() else "arquivo",
                      "motivo": f"não é uma cópia desta skill (o SKILL.md não declara name: {NOME}); resolva "
                                "manualmente"})
    if PREPARO.exists():
        plano.append({"caminho": str(PREPARO), "acao": "remover", "tipo": "área de preparo (sobras de troca)"})
    return plano


def remover(plano: list[dict]) -> dict:
    removidos, mantidos, falhas = [], [], []
    for item in plano:
        caminho = Path(item["caminho"])
        if item["acao"] != "remover":
            mantidos.append(item)
            continue
        try:
            if e_ligacao(caminho):
                os.rmdir(caminho) if os.name == "nt" else caminho.unlink()  # só a ligação, nunca o alvo
            else:
                apagar_arvore(caminho)
            removidos.append(item)
        except OSError as e:
            falhas.append({**item, "erro": f"{type(e).__name__}: {e}"})
    restam = [str(p) for p in (CLAUDE, AGENTS) if os.path.lexists(p)]
    return {"removido": not restam, "removidos": removidos, "mantidos": mantidos, "falhas": falhas,
            "restam": restam}


def instalar_ou_atualizar(acao: str, pasta: Path, integridade: dict) -> dict:
    referencia = referencia_de(pasta)
    recuperacao = concluir_troca_interrompida()
    passos = [f"troca interrompida concluída: {recuperacao['acao']}"] if recuperacao else []
    if recuperacao and recuperacao.get("orfas_removidas"):
        passos.append(f"marca de troca ilegível: cópia(s) preparada(s) órfã(s) removida(s) de {PREPARO}: "
                      + ", ".join(recuperacao["orfas_removidas"]))
    if recuperacao and recuperacao.get("orfas_nao_removidas"):
        passos.append(f"sobras em {PREPARO} que não puderam ser removidas: "
                      + "; ".join(recuperacao["orfas_nao_removidas"]))
    if recuperacao and acao == "instalar" and (AGENTS.exists() or e_ligacao(AGENTS)):
        acao = "atualizar"  # a troca concluída deixou uma versão no lugar: segue como atualização
    if acao == "instalar" and (AGENTS.exists() or e_ligacao(AGENTS)):
        raise Recusa(f"{AGENTS} já existe; use 'atualizar'")
    if AGENTS.exists() and not e_ligacao(AGENTS) and nome_declarado(AGENTS) != NOME:
        # A troca guardaria em skills-anteriores, como se fosse versão desta skill, o que não é (A02).
        raise Recusa(f"{AGENTS} existe, mas não é uma cópia desta skill (o SKILL.md não declara name: {NOME}); "
                     "nada foi alterado. Confira o conteúdo e retire-o manualmente",
                     name_no_destino=nome_declarado(AGENTS))
    conferir_ligacao_antes()
    preparo = preparar_copia(pasta, referencia)
    anterior = promover(preparo)
    limpar_preparo()
    if anterior is not None:
        passos.append(f"versão anterior guardada em {anterior}")
    passos.append("cópia instalada")
    try:
        passos.append(ligar())
    except BaseException as erro:
        desfazer(anterior, erro)
        raise
    res = verificar(referencia)
    res["passos"] = passos
    res["integridade_do_pacote"] = integridade
    return res


PYTHON_MINIMO = (3, 10)  # do instalador; o núcleo e as integrações têm requisitos próprios (README-ENTREGA)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("acao", choices=["instalar", "atualizar", "verificar", "remover"])
    ap.add_argument("--origem", type=Path)
    ap.add_argument("--sha256", help="hash SHA-256 do pacote, recebido por OUTRO canal (quem publicou a versão; o "
                                     "pipeline que gerou o pacote); obrigatório em instalar e atualizar")
    ap.add_argument(OPCAO_PASTA_DEV, action="store_true",
                    help="SÓ DESENVOLVIMENTO, INSEGURO: aceita uma PASTA como origem de instalar/atualizar sem "
                         "nenhum hash independente; desligada por padrão, e a saída avisa")
    ap.add_argument("--confirmar", action="store_true")
    a = ap.parse_args()
    if tuple(sys.version_info[:2]) < PYTHON_MINIMO:
        # Pré-verificação ANTES de qualquer alteração: nada é copiado nem ligado (F17).
        print(json.dumps({"erro": f"o instalador exige Python {PYTHON_MINIMO[0]}.{PYTHON_MINIMO[1]} ou posterior "
                                  f"(encontrado {sys.version_info[0]}.{sys.version_info[1]}); nada foi alterado"},
                         ensure_ascii=False))
        return 2
    if a.acao == "remover":
        plano = planejar_remocao()
        if not a.confirmar:
            print(json.dumps({"erro": "remoção exige --confirmar",
                              "removeria": [i["caminho"] for i in plano if i["acao"] == "remover"],
                              "manteria": [i for i in plano if i["acao"] != "remover"]}, ensure_ascii=False))
            return 1
        res = remover(plano)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["removido"] else 1
    if a.acao == "verificar" and not a.origem:
        res = verificar()
        res["aviso"] = "sem --origem, os hashes não foram comparados"
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["ok"] else 1
    if not a.origem:
        ap.error("informe --origem")
    try:
        origem = a.origem.resolve()
        if not origem.exists():
            raise Recusa(f"{origem} não existe; nada foi alterado")
        altera = a.acao in ("instalar", "atualizar")
        sha = sha_informado(a.sha256)
        dados, aviso = None, None
        if origem.is_dir():
            if sha:
                raise Recusa("--sha256 vale para pacote (.skill ou .zip), não para pasta; nada foi alterado")
            if altera and not a.pasta_de_desenvolvimento_nao_verificada:
                raise Recusa(f"pasta como origem não tem hash independente: use o pacote com --sha256 ou, só em "
                             f"desenvolvimento, {OPCAO_PASTA_DEV}; nada foi alterado")
            integridade = {"sha256": None, "conferido_com": [], "ok": None, "autenticado_por": None,
                           "nota": "origem é pasta: não há hash de pacote"}
            if altera:
                aviso = (f"ORIGEM NÃO VERIFICADA ({OPCAO_PASTA_DEV}): pasta instalada sem hash independente; "
                         "use só em desenvolvimento, nunca para distribuir")
        else:
            if a.pasta_de_desenvolvimento_nao_verificada:
                raise Recusa(f"{OPCAO_PASTA_DEV} vale só para pasta; para pacote, informe --sha256; nada foi alterado")
            if altera and not sha:
                raise Recusa(f"{a.acao} exige --sha256 com o hash do pacote recebido por outro canal (quem publicou a "
                             "versão; o pipeline que gerou o pacote). O SHA256SUMS.txt ao lado viaja no mesmo canal "
                             "do pacote e não o autentica; nada foi alterado")
            dados = ler_pacote(origem)  # lido uma vez: o hash e a extração usam os mesmos bytes (#3)
            integridade = integridade_do_pacote(origem, dados, sha)
        with tempfile.TemporaryDirectory() as td:
            pasta = origem_como_pasta(origem, Path(td), dados)
            if a.acao == "verificar":
                res = verificar(referencia_de(pasta))
                res["integridade_do_pacote"] = integridade
            else:
                res = instalar_ou_atualizar(a.acao, pasta, integridade)
        if aviso:
            res["aviso"] = aviso
    except Recusa as r:
        print(json.dumps({**r.dados, "estado_atual": verificar()}, ensure_ascii=False, indent=2))
        return 1
    except OSError as e:
        print(json.dumps({"erro": f"falha durante a operação ({type(e).__name__}: {e}); a versão que estava "
                                  "instalada é mantida ou devolvida ao lugar — confira estado_atual",
                          "estado_atual": verificar()}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
