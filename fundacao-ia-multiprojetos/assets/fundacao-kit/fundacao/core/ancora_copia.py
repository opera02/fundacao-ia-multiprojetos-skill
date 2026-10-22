"""Âncora externa da cópia (varredura da 1.4.5, #8) e quem pode verificar ou restaurar (auditoria Codex Security da
1.7.6, #2). Saiu de backup.py na 1.7.7; backup.py reexporta os nomes.

- O manifesto fica na pasta da cópia: quem reescreve a pasta recalcula tudo. A âncora é o SHA-256 do manifest.json,
  devolvido pelo `backup criar` e anotado no livro de cópias (`state/copias.jsonl`, ao lado do registro protegido e
  fora da cópia). O manifesto é lido uma vez: a âncora confere os mesmos bytes que valem depois.
- O livro só vale tanto quanto `state/` está protegido: no perfil de dados reais do WSL, a sessão grava `state/` e a
  pasta de backups, e quem grava as duas troca a cópia e anota a âncora nova. A âncora vinda do livro sai com aviso;
  depois de suspeita de comprometimento, vale o sha256_manifesto guardado fora. Livro e registro dentro da própria
  cópia não valem (revisão de segurança da 1.7.7, R177-KIT-01). Assinar as entradas do livro fica como proposta.
- A autorização não vem de cópia não autenticada [Decisão; auditoria da 1.7.6, #2]. Com a fundação viva (banco legível
  na raiz, que não é restauração não liberada nem a própria cópia — igual a ela, dentro dela ou com o manifesto de
  uma cópia: R177-KIT-02; nem com o banco dela, por ligação ou vínculo físico, ou ligação no caminho do banco: segunda
  passada da revisão), vale a política dela — a atual: quem perdeu a administração depois da
  cópia não restaura, e uma ACL forjada na cópia não conta. Sem ela (origem perdida ou danificada), vale a política DA
  CÓPIA, e só depois de a âncora conferir o manifesto e o banco conferir com o `db_sha256` do manifesto ancorado — numa
  cópia privada do banco, não no lugar. Sem as duas, ninguém: na recuperação de desastre, o sha256_manifesto guardado
  fora da cópia (ou o livro guardado junto do registro, fora da cópia) é a prova. Limite: outra pasta com um banco
  forjado ainda passa por fundação viva — a raiz é a que o lançador entrega, e a resposta mostra a raiz resolvida.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path, PureWindowsPath

from . import preparo, publicacao
from .auth import Policy, principal_from_env
from .canon import canonical_json, sha256_bytes
from .contracts import AccessDenied, ValidationError
from .db import conectar_copia, conectar_somente_leitura

LIVRO_COPIAS = "copias.jsonl"  # âncoras das cópias (sha256 do manifest.json), ao lado do registro protegido
MARCA_NAO_LIBERADA = "restauracao-nao-liberada.json"  # raiz restaurada ainda não liberada: a CLI recusa usá-la
FONTE_INFORMADA, FONTE_LIVRO = "sha256 informado", "livro de cópias"  # de onde veio a âncora que conferiu
GUARDE_A_ANCORA = ("guarde o sha256_manifesto FORA da pasta da cópia (anotação, gerenciador de senhas, outro disco); "
                   "ele também foi anotado em state/copias.jsonl — guarde esse livro junto do registro protegido "
                   "(state/retiradas.jsonl). A restauração confere a cópia por ele; sem a fundação viva, é ele que "
                   "autoriza quem restaura.")
AVISO_SEM_ANCORA = ("ATENÇÃO: nada fora da pasta da cópia confirma que ela é a que foi guardada; quem pode escrever "
                    "nessa pasta pode trocar arquivos, banco e permissões e recalcular o manifesto. Confira com o "
                    "sha256_manifesto devolvido pelo `backup criar` (--sha256-manifesto) ou com o livro de cópias "
                    "(state/copias.jsonl) ao lado do registro protegido.")
AVISO_ANCORA_DO_LIVRO = ("a cópia foi conferida pelo livro de cópias (state/copias.jsonl), não por um sha256_manifesto "
                         "guardado fora: o livro só vale tanto quanto state/ está protegido. No perfil de dados reais do "
                         "WSL, a sessão grava state/ e a pasta de backups, e quem grava as duas troca a cópia e anota a "
                         "âncora nova no livro. Depois de suspeita de comprometimento, restaure com o sha256_manifesto "
                         "guardado fora (--sha256-manifesto).")


def _caminho_valido(rel) -> bool:
    """Caminho do manifesto como o backup grava: relativo, com `/`, sem `.`/`..` e fora de `state/` — a verificação
    nunca lê fora da pasta `files/` da cópia (#12). No Windows, `\\` e `C:` também mudariam o caminho."""
    if not isinstance(rel, str) or not rel or rel.startswith("/"):
        return False
    partes, janela = rel.split("/"), PureWindowsPath(rel)
    return (not any(p in ("", ".", "..") for p in partes) and partes[0] != "state"
            and (os.name != "nt" or not (janela.drive or janela.root or ".." in janela.parts)))


def ler_manifesto(bruto: bytes) -> dict:
    """Manifesto com a estrutura esperada (e caminhos dentro da cópia); senão, erro do contrato (não traceback)."""
    try:
        m = json.loads(bruto.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        m = None
    ok = (isinstance(m, dict) and isinstance(m.get("files"), list)
          and all(isinstance(f, dict) and _caminho_valido(f.get("path")) and isinstance(f.get("sha256"), str)
                  for f in m["files"])
          and isinstance(m.get("db"), (dict, type(None))) and isinstance(m.get("retiradas"), (dict, type(None))))
    if not ok:
        raise ValidationError("manifesto da cópia com estrutura inválida: não é uma cópia desta fundação")
    return m


def anotar_ancora(livro: Path, registro: dict) -> None:
    """Acrescenta a âncora ao livro por `publicacao.anexar`: ligação ou vínculo físico no lugar do livro recusa sem
    gravar (revisão de segurança da 1.7.7, R177-KIT-04: com `open("a")`, a linha ia para o arquivo de fora)."""
    livro.parent.mkdir(parents=True, exist_ok=True)
    publicacao.anexar(livro, (canonical_json(registro) + "\n").encode("utf-8"))


def _ancoras_do_livro(livro: Path) -> set[str]:
    """Âncoras anotadas no livro de cópias; linha ilegível não confere nada (só deixa de achar)."""
    try:
        linhas = livro.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return set()
    ancoras = set()
    for linha in linhas:
        try:
            rec = json.loads(linha)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict) and isinstance(rec.get("sha256_manifesto"), str):
            ancoras.add(rec["sha256_manifesto"])
    return ancoras


def _real(caminho) -> Path:
    try:
        return Path(caminho).resolve()
    except (OSError, RuntimeError):  # ligação em laço ou nome que o sistema recusa: o caminho absoluto, sem resolver
        return Path(os.path.abspath(caminho))


def dentro_da_copia(caminho, origem) -> bool:
    """`caminho` é a própria pasta da cópia (`origem`) ou fica dentro dela, com as ligações resolvidas e, onde o
    sistema dá identidade de arquivo, também pelo objeto do disco (dispositivo e inode de cada ancestral): caixa
    diferente, nome curto do Windows ou ligação não escondem (revisão de segurança da 1.7.7, R177-KIT-01 e 02)."""
    alvo, pasta = _real(caminho), _real(origem)
    if alvo == pasta or alvo.is_relative_to(pasta):
        return True
    try:
        st = os.stat(pasta)
    except OSError:
        return False
    if not st.st_ino:  # sistema de arquivos sem identidade (alguns compartilhamentos): vale só o caminho
        return False
    for ancestral in (alvo, *alvo.parents):
        try:
            atual = os.stat(ancestral)
        except OSError:
            continue
        if (atual.st_dev, atual.st_ino) == (st.st_dev, st.st_ino):
            return True
    return False


def _mesmo_arquivo(a: Path, b: Path) -> bool:
    """`a` e `b` são o mesmo objeto do disco (vínculo físico), onde o sistema dá identidade de arquivo."""
    try:
        sa, sb = os.stat(a), os.stat(b)
    except (OSError, ValueError):
        return False
    return bool(sa.st_ino) and (sa.st_dev, sa.st_ino) == (sb.st_dev, sb.st_ino)


def conferir_ancora(bruto: bytes, sha256_manifesto: str | None = None, livro: Path | None = None,
                    origem: Path | None = None) -> dict:
    """Confere os bytes do manifest.json da cópia contra a âncora guardada FORA dela (#8): a informada pelo operador
    (`fonte`: sha256 informado) ou a anotada no livro de cópias (`fonte`: livro de cópias, e `livro`). `situacao`:
    conferida, divergente (a informada não bate) ou ausente (com `livro_sem_esta_copia` quando o livro existe e não a
    tem). Livro dentro da própria cópia (`origem`) não vale: ausente, com o motivo em `livro_recusado` (R177-KIT-01)."""
    atual = sha256_bytes(bruto)
    if sha256_manifesto:
        situacao = "conferida" if sha256_manifesto.strip().lower() == atual else "divergente"
        return {"situacao": situacao, "fonte": FONTE_INFORMADA, "sha256_manifesto": atual}
    ausente = {"situacao": "ausente", "fonte": None, "sha256_manifesto": atual}
    if livro is not None and origem is not None and dentro_da_copia(livro, origem):
        return {**ausente, "livro_recusado": f"o livro de cópias informado ({livro}) fica dentro da própria cópia: "
                                             "não vale como âncora"}
    if livro is not None and Path(livro).is_file():
        if atual in _ancoras_do_livro(Path(livro)):
            return {"situacao": "conferida", "fonte": FONTE_LIVRO, "livro": str(livro), "sha256_manifesto": atual}
        return {**ausente, "livro_sem_esta_copia": str(livro)}
    return ausente


def aviso_da_ancora(ancora: dict) -> dict:
    """`aviso_ancora` da resposta: sem âncora, o de sempre; âncora vinda do livro, o limite dele (R177-KIT-01)."""
    if ancora["situacao"] == "ausente":
        return {"aviso_ancora": AVISO_SEM_ANCORA}
    return {"aviso_ancora": AVISO_ANCORA_DO_LIVRO} if ancora.get("fonte") == FONTE_LIVRO else {}


def motivo_sem_ancora(ancora: dict) -> str:
    """Por que a âncora não conferiu, para a recusa: sem ela, não se libera nem se autoriza pela cópia."""
    if ancora["situacao"] == "divergente":
        return "o sha256_manifesto informado não confere com o manifesto dela"
    if ancora.get("livro_recusado"):
        return ancora["livro_recusado"]
    if ancora.get("livro_sem_esta_copia"):
        return f"ela não consta no livro de cópias ao lado do registro ({LIVRO_COPIAS})"
    return "nada fora da pasta da cópia a confirma"


def autorizar(raiz: Path, origem: Path, *, sha256_manifesto: str | None = None, livro: Path | None = None) -> dict:
    """Quem pode verificar ou restaurar a cópia em `origem`: a administração da fundação, decidida por uma política
    confiável (#2). Devolve {"identidade", "politica", "raiz"} — a raiz resolvida; sem fundação viva, também o motivo
    (`sem_fundacao_viva`) — ou AccessDenied: a negativa não vai para trilha nenhuma (a origem pode estar danificada,
    e a cópia só é lida).
    - Fundação viva (`<raiz>/state/state.sqlite` legível, raiz que não é restauração não liberada nem a própria cópia:
      R177-KIT-02; banco que não é o da cópia e sem ligação no caminho: segunda passada): a política dela.
    - Sem ela: a política da cópia, se a âncora (`sha256_manifesto` ou o livro, fora da cópia: R177-KIT-01) conferir
      o manifesto e o banco conferir com o `db_sha256` dele — o banco é lido de uma cópia privada, conferida antes de
      aberta.
    - Sem as duas: ninguém. A negativa diz por que a raiz não valeu e lembra o `--raiz` (quem roda fora da raiz não
      está num desastre)."""
    real = str(_real(raiz))
    viva, sem_viva = _fundacao_viva(Path(raiz), Path(origem))
    if viva is not None:
        return {**viva, "raiz": real}
    origem = Path(origem)
    bruto = preparo.ler(origem / "manifest.json")
    manifest = ler_manifesto(bruto)
    ancora = conferir_ancora(bruto, sha256_manifesto, livro, origem)
    if ancora["situacao"] != "conferida" or not manifest.get("db_sha256"):
        motivo = (motivo_sem_ancora(ancora) if ancora["situacao"] != "conferida"
                  else "cópia anterior à 1.3.1, sem o hash do banco no manifesto")
        raise AccessDenied(f"a raiz {real} não vale como fundação viva ({sem_viva}): se a fundação existe, rode na "
                           "pasta dela ou informe --raiz <pasta da fundação>. Sem ela, só a cópia autenticada pela "
                           f"âncora diz quem pode verificá-la ou restaurá-la, e ela não se autenticou ({motivo}): "
                           "informe --sha256-manifesto (o código devolvido pelo `backup criar`, guardado fora da cópia) "
                           "ou use o livro de cópias da fundação, fora da cópia (ao verificar, o de <raiz>/state; ao "
                           "restaurar, o que fica ao lado de --retiradas)", action="admin", resource="foundation")
    with tempfile.TemporaryDirectory(prefix="fundacao-autorizacao-", ignore_cleanup_errors=True) as pasta:
        banco, origem_db = Path(pasta) / "state.sqlite", origem / "state" / "state.sqlite"
        if (preparo.ligacao_no_caminho(origem_db) or not origem_db.is_file()
                or preparo.copiar(origem_db, banco, os.lstat(origem_db))[0] != manifest["db_sha256"]):
            raise AccessDenied("o banco da cópia falta, passa por ligação ou não confere com o manifesto ancorado: a "
                               "cópia não autoriza ninguém", action="admin", resource="foundation")
        return {**_administra(conectar_copia(banco), "cópia autenticada pela âncora"), "raiz": real,
                "sem_fundacao_viva": sem_viva}


def _fundacao_viva(raiz: Path, origem: Path) -> tuple[dict | None, str]:
    """(política da fundação viva, "") ou (None, por que a raiz não vale como fundação viva): a própria cópia — igual
    a ela, dentro dela ou com o manifesto de uma cópia, onde a ACL é a que a cópia traz (R177-KIT-02) —, o banco da
    cópia numa pasta nova (`state/` ligado ao dela ou vínculo físico com o banco dela) ou ligação no caminho do banco
    (segunda passada da revisão, variante do R177-KIT-02), restauração não liberada, ou banco ausente, ilegível ou
    sem a ACL (origem perdida ou danificada: decide a cópia autenticada)."""
    banco = raiz / "state" / "state.sqlite"
    if dentro_da_copia(raiz, origem):
        return None, "é a própria cópia ou fica dentro dela"
    if dentro_da_copia(banco, origem) or _mesmo_arquivo(banco, Path(origem) / "state" / "state.sqlite"):
        return None, "o banco state/state.sqlite é o da própria cópia (por ligação ou vínculo físico)"
    if os.path.lexists(raiz / "manifest.json"):
        return None, "tem o manifest.json de uma cópia de backup"
    ligada = preparo.ligacao_no_caminho(banco)  # como no `backup criar`: a ligação leva o banco para outro lugar
    if ligada:
        return None, f"o caminho do banco state/state.sqlite passa por ligação ({ligada}): informe o caminho real"
    if (raiz / "state" / MARCA_NAO_LIBERADA).exists():
        return None, "é uma restauração não liberada"
    if not banco.is_file():
        return None, "sem o banco de estado state/state.sqlite"
    con = None
    try:
        con = conectar_somente_leitura(banco)
        con.execute("SELECT (SELECT 1 FROM principal LIMIT 1), (SELECT 1 FROM acl LIMIT 1)").fetchone()
    except sqlite3.DatabaseError:
        if con is not None:
            con.close()
        return None, "banco de estado ilegível ou danificado"
    return _administra(con, "fundação viva"), ""


def _administra(con: sqlite3.Connection, politica: str) -> dict:
    try:
        me = principal_from_env(con)
        if not Policy(con).allowed(me.principal_id, "admin", "foundation"):
            raise AccessDenied(f"restauração e verificação exigem administração da fundação (conferida na {politica})",
                               action="admin", resource="foundation")
        return {"identidade": me.principal_id, "politica": politica}
    finally:
        con.close()
