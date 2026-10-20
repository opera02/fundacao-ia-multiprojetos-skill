#!/usr/bin/env python3
"""Instala, atualiza, verifica ou remove a skill fundacao-ia-multiprojetos neste computador.

Convenção (a mesma já usada pelas outras skills deste perfil):
  cópia física   ~/.agents/skills/fundacao-ia-multiprojetos        (Codex e outros hosts Agent Skills)
  ligação        ~/.claude/skills/fundacao-ia-multiprojetos  ->  cópia física
                 (Windows: junção de diretório, sem exigir administrador; Linux/macOS: link simbólico)

  python instalar_skill.py instalar   --origem <pasta-da-skill | pacote.skill> [--sha256 <hash>]
  python instalar_skill.py atualizar  --origem <...> [--sha256 <hash>]  (guarda a anterior em ~/.agents/skills-anteriores/)
  python instalar_skill.py verificar [--origem <...>] [--sha256 <hash>]  (ligação; com --origem, compara os hashes)
  python instalar_skill.py remover                        (pede --confirmar; remove a ligação, a cópia e a
                                                           instalação manual desta skill em ~/.claude/skills)

Somente arquivos locais; nada é baixado. Saída em JSON, também nos erros.
Requer Python 3.10 ou posterior, conferido ANTES de qualquer alteração. A junção do Windows é
reconhecida também sem `os.path.isjunction` (que só existe a partir do 3.12), pela marca de ponto
de montagem do `lstat` — assim verificar, atualizar e remover funcionam no 3.10/3.11.

Integridade do pacote, ANTES de extrair: com `--sha256` (hash recebido por outro canal) e com o
`SHA256SUMS.txt` que estiver ao lado do pacote, se ele listar o arquivo. Qualquer divergência recusa a
operação sem alterar nada; sem nenhum dos dois, a saída diz que o hash não foi conferido.

Instalar e atualizar trocam a versão por renomeação: a versão nova é copiada para uma área de preparo
FORA das pastas de skills (~/.agents/skills-preparo/), conferida contra o pacote e só então posta no
lugar — a anterior vai para ~/.agents/skills-anteriores/ e a preparada entra no lugar dela (DUAS
renomeações, com uma marca de troca entre elas). Uma falha antes disso não altera nada; uma exceção na
troca ou na ligação devolve a versão anterior e descarta a cópia preparada; se o processo cair entre as
duas renomeações, o próximo `instalar` ou `atualizar` conclui a troca com a cópia preparada (já
conferida), e o `verificar` avisa enquanto isso não acontecer (auditoria final da 1.4.2, AF-02); se a
marca da troca estiver ilegível, as cópias preparadas que sobrarem em skills-preparo são removidas e
relatadas em `passos`, em vez de ficarem órfãs (conferência da 1.4.3, CF-04).
Ligação em conflito é recusada antes de copiar. A origem precisa declarar `name: fundacao-ia-multiprojetos`
no SKILL.md (AF-03; UTF-8 com BOM aceito, e a recusa diz quando não há `name` legível, CF-03).

`remover` relata cada caminho e sai com código 1 se algo ficar no lugar; arquivo somente leitura
não o interrompe; a área de preparo (sobras) também é removida; uma ligação em ~/.claude/skills com o
nome desta skill que aponte para a pasta de OUTRA skill é mantida e relatada (AF-04), mas se o alvo
não existir mais (ligação pendurada) só a ligação é removida e relatada (CF-02). `verificar`
informa se o SQLite tem o FTS5 com o tokenizador do kit da fundação: é só informativo e não entra em
`ok` (a skill instalada não depende dele; o kit, sim).
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
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


def integridade_do_pacote(origem: Path, sha_informado: str | None) -> dict:
    """Confere o hash do pacote ANTES de extrair. Divergência com `--sha256` ou com o SHA256SUMS.txt ao
    lado (se ele listar o arquivo) recusa a operação; nada é alterado."""
    if origem.is_dir():
        if sha_informado:
            raise Recusa("--sha256 vale para pacote (.skill ou .zip), não para pasta; nada foi alterado")
        return {"sha256": None, "conferido_com": [], "ok": None, "nota": "origem é pasta: não há hash de pacote"}
    atual = hashlib.sha256(origem.read_bytes()).hexdigest()
    res = {"sha256": atual, "conferido_com": [], "ok": None}
    esperados = []
    if sha_informado:
        esperados.append(("--sha256", sha_informado.strip().lower()))
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
    if esperados:
        res["ok"] = True
    else:
        res.setdefault("nota", "sem --sha256 e sem SHA256SUMS.txt ao lado: hash do pacote não conferido")
    return res


def origem_como_pasta(origem: Path, tmp: Path) -> Path:
    if origem.is_dir():
        if not (origem / "SKILL.md").exists():
            raise Recusa(f"{origem} não contém SKILL.md; nada foi alterado")
        pasta = origem
    else:
        try:
            with zipfile.ZipFile(origem) as z:
                z.extractall(tmp)  # o zipfile tira unidade, raiz e componentes `..` dos nomes
        except (zipfile.BadZipFile, zlib.error, EOFError, OSError, RuntimeError, NotImplementedError) as e:
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


def ligacao_aponta_para_copia() -> bool:
    return e_ligacao(CLAUDE) and CLAUDE.resolve() == AGENTS.resolve()


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
    Uma exceção na segunda renomeação devolve a anterior e descarta a cópia preparada (AF-02)."""
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
    except BaseException:
        if anterior is not None and not os.path.lexists(AGENTS):
            os.replace(anterior, AGENTS)  # devolve a anterior ao lugar
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


def desfazer(anterior: Path | None) -> None:
    """Depois de promover: retira a versão nova e, se havia uma anterior, devolve-a ao lugar."""
    descarte = caminho_livre(PREPARO / f"{NOME}-descartada")
    PREPARO.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(AGENTS):
        os.replace(AGENTS, descarte)
    if anterior is not None:
        os.replace(anterior, AGENTS)
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
    elif AGENTS.exists():
        plano.append({"caminho": str(AGENTS), "acao": "remover", "tipo": "cópia"})
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
    conferir_ligacao_antes()
    preparo = preparar_copia(pasta, referencia)
    anterior = promover(preparo)
    limpar_preparo()
    if anterior is not None:
        passos.append(f"versão anterior guardada em {anterior}")
    passos.append("cópia instalada")
    try:
        passos.append(ligar())
    except BaseException:
        desfazer(anterior)
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
    ap.add_argument("--sha256", help="hash SHA-256 esperado do pacote, recebido por outro canal")
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
        integridade = integridade_do_pacote(origem, a.sha256)
        with tempfile.TemporaryDirectory() as td:
            pasta = origem_como_pasta(origem, Path(td))
            if a.acao == "verificar":
                res = verificar(referencia_de(pasta))
                res["integridade_do_pacote"] = integridade
            else:
                res = instalar_ou_atualizar(a.acao, pasta, integridade)
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
