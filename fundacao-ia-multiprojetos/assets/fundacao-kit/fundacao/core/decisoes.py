r"""Decisões do titular assinadas: a barreira fora do alcance do executor (DECISAO-003 da fundação de referência).

Aceite, pedido de correção e rejeição de uma entrega valem com a assinatura `ssh-keygen -Y` do titular, no
namespace `fundacao-decisao`, conferida contra a âncora `allowed_signers` que só um administrador altera
(`C:\ProgramData\FundacaoIA\confianca\allowed_signers` no Windows). A chave privada tem senha que só o titular
sabe. O executor prepara a decisão — JSON canônico com o SHA-256 da entrega exata —, o titular lê e assina no
PRÓPRIO terminal, e a conferência pode ser refeita por ele com o ssh-keygen do sistema, sem depender deste código.

Conferência (`verificar_decisao`), sem alterar nada: decisão dentro de `decisoes/` do projeto, no esquema e na forma
canônica; entrega dentro de `outputs/` com o mesmo SHA-256; assinatura no namespace da barreira, de uma chave da
âncora cujo dono é o `assinante` da decisão; e `ssh-keygen -Y verify` do sistema, por caminho fixo (um `ssh-keygen`
posto antes no PATH não decide nada).

Limites (registre sempre): protege as decisões, não isola os projetos; quem roda esta conferência é o executor,
então a prova independente é o titular repetir `ssh-keygen -Y verify` no próprio terminal.
"""

from __future__ import annotations

import base64
import fnmatch
import hashlib
import json
import os
import re
import shutil
import stat
import struct
import subprocess
import tempfile
import time
import uuid
from pathlib import Path, PureWindowsPath

from . import events
from .auth import Policy, Principal, resource_project
from .canon import sha256_bytes
from .contracts import AccessDenied, AlreadyExists, NotFound, ValidationError
from .paths import contained
from .projects import project_root, projects_dir
from .tasks import Budget, Coordinator, PermanentError, StepDef

NAMESPACE = "fundacao-decisao"
SCHEMA = "fundacao.decisao_assinada/1"
TIPOS = ("aceite", "correcao", "rejeicao")
CAMPOS = ("schema_version", "decisao_id", "project_id", "task_id", "tipo", "motivo", "assinante", "namespace",
          "entrega")
ANCORA_WINDOWS = r"C:\ProgramData\FundacaoIA\confianca\allowed_signers"
SSH_KEYGEN_WINDOWS = r"C:\Windows\System32\OpenSSH\ssh-keygen.exe"  # o do sistema, visto do WSL
CHAVE_DO_TITULAR = "fundacao_titular"  # em ~/.ssh: gerada pelo titular, com senha
SHELLS = ("powershell", "bash")
ANCORA_WSL = "/mnt/c/ProgramData/FundacaoIA/confianca/allowed_signers"  # a do Windows, vista do WSL
ANCORA_POSIX = "/etc/fundacao-ia/confianca/allowed_signers"  # Linux fora do WSL: dono root
# Lugar fixo da âncora (só o administrador altera); a primeira que existir vale nesta máquina.
ANCORAS_PADRAO = (ANCORA_WINDOWS,) if os.name == "nt" else (ANCORA_WSL, ANCORA_POSIX)
POLITICA = "politica-decisoes.json"  # em registry/
SCHEMA_POLITICA = "fundacao.politica_decisoes/1"
REGISTRO = "registro.jsonl"  # em projects/<p>/decisoes/, formato da ferramenta da fundação
EVENTO_ASSINADA = "decisao_assinada_registrada"
FLUXO_ACEITE = "aceite-assinado"  # mesmo fluxo e etapa da ferramenta da fundação: repetir devolve a execução
ETAPA_ACEITE = "conferir-aceite"
EVENTO_SEM_ASSINATURA = "decisao_registrada_sem_assinatura"
DECISAO_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_CHAVE_RE = re.compile(r"(ssh-ed25519|ssh-rsa|ecdsa-sha2-[a-z0-9]+|sk-ssh-ed25519@openssh\.com"
                       r"|sk-ecdsa-sha2-nistp256@openssh\.com)\s+([A-Za-z0-9+/=]+)")


class DecisaoInvalida(ValidationError, ValueError):
    """Decisão malformada: erro do contrato da CLI (código 2) e também ValueError, como na ferramenta da fundação."""


def canonico(decisao: dict) -> bytes:
    """Bytes que o titular assina: JSON com chaves ordenadas, recuo de 2, UTF-8 sem escapes e quebra de linha no fim
    — a forma das decisões já registradas pela ferramenta da fundação (não é o `canonical_json` compacto do kit)."""
    return (json.dumps(decisao, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def sha256_arquivo(caminho) -> str:
    return sha256_bytes(Path(caminho).read_bytes())


def montar_decisao(*, projeto: str, tarefa: str, entrega_rel: str, entrega_sha256: str, tipo: str, motivo: str,
                   assinante: str, decisao_id: str, agora: str) -> dict:
    if tipo not in TIPOS:
        raise DecisaoInvalida("tipo deve ser um de " + ", ".join(TIPOS), tipo=tipo)
    if not str(motivo).strip():
        raise DecisaoInvalida("motivo vazio: a decisão precisa das palavras do titular")
    if not DECISAO_ID_RE.match(str(decisao_id)):
        raise DecisaoInvalida("identificador da decisão inválido: use letras, números, ponto, hífen e sublinhado",
                              decisao_id=decisao_id)
    return {"schema_version": SCHEMA, "decisao_id": decisao_id, "project_id": projeto, "task_id": tarefa,
            "tipo": tipo, "motivo": motivo.strip(), "assinante": assinante, "namespace": NAMESPACE,
            "entrega": {"caminho": entrega_rel, "sha256": entrega_sha256}, "preparado_em": agora}


# ------------------------------------------------------------------ chaves, âncora e assinatura
def _impressao_do_blob(blob: bytes) -> str:
    """SHA256:<base64 sem '='> do blob da chave pública (igual ao `ssh-keygen -l`)."""
    return "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode("ascii").rstrip("=")


def impressao_digital(linha_chave: str) -> str | None:
    m = _CHAVE_RE.search(linha_chave)
    if not m:
        return None
    try:
        return _impressao_do_blob(base64.b64decode(m.group(2), validate=True))
    except ValueError:
        return None


def ler_ancora(ancora) -> list[dict]:
    """Linhas do `allowed_signers`: principais (primeiro campo, separados por vírgula), namespaces permitidos e a
    impressão digital da chave. Comentários e linhas vazias ficam de fora."""
    linhas = []
    for bruta in Path(ancora).read_text(encoding="utf-8").splitlines():
        if not bruta.strip() or bruta.lstrip().startswith("#"):
            continue
        principal = bruta.split()[0]
        ns = re.search(r'namespaces="([^"]*)"', bruta)
        linhas.append({"principal": principal, "principais": principal.split(","),
                       "namespaces": ns.group(1).split(",") if ns else None,
                       "impressao_digital": impressao_digital(bruta)})
    return linhas


def _string_ssh(blob: bytes, pos: int) -> tuple[bytes, int]:
    if pos + 4 > len(blob):
        raise ValueError("assinatura truncada")
    (n,) = struct.unpack(">I", blob[pos:pos + 4])
    if pos + 4 + n > len(blob):
        raise ValueError("assinatura truncada")
    return blob[pos + 4:pos + 4 + n], pos + 4 + n


def _campos_da_assinatura(bruto: bytes) -> dict:
    texto = bruto.decode("ascii")
    m = re.search(r"-----BEGIN SSH SIGNATURE-----(.*?)-----END SSH SIGNATURE-----", texto, re.S)
    if not m:
        raise ValueError("assinatura sem a moldura SSH SIGNATURE")
    blob = base64.b64decode("".join(m.group(1).split()), validate=True)
    if blob[:6] != b"SSHSIG" or len(blob) < 10:
        raise ValueError("assinatura sem o prefixo SSHSIG")
    (versao,) = struct.unpack(">I", blob[6:10])
    campos, pos = [], 10
    for _ in range(5):  # chave pública, namespace, reservado, algoritmo de hash, assinatura
        valor, pos = _string_ssh(blob, pos)
        campos.append(valor)
    if pos != len(blob):
        raise ValueError("assinatura com bytes a mais")
    chave, namespace, _reservado, algoritmo, _assinatura = campos
    return {"versao": versao, "namespace": namespace.decode("utf-8", "replace"),
            "hash": algoritmo.decode("ascii", "replace"), "impressao_digital": _impressao_do_blob(chave)}


def ler_assinatura(sig) -> dict:
    """Campos da assinatura SSHSIG (PROTOCOL.sshsig do OpenSSH), sem conferir a criptografia: namespace e impressão
    digital da chave que assinou. Servem para dizer POR QUE uma assinatura não vale; quem decide se ela confere com o
    conteúdo é o `ssh-keygen -Y verify`."""
    return _campos_da_assinatura(Path(sig).read_bytes())


def ssh_keygen_do_sistema() -> str | None:
    """Caminho fixo do ssh-keygen do sistema, se existir: no Windows, a pasta de sistema vem da API (não do PATH nem
    de variável de ambiente); nos demais, /usr/bin."""
    if os.name == "nt":
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        n = ctypes.windll.kernel32.GetSystemDirectoryW(buf, len(buf))
        candidato = Path(buf.value) / "OpenSSH" / "ssh-keygen.exe" if n else None
    else:
        candidato = Path("/usr/bin/ssh-keygen")
    return str(candidato) if candidato is not None and candidato.is_file() else None


def ssh_keygen() -> str:
    exe = ssh_keygen_do_sistema() or shutil.which("ssh-keygen")
    if not exe:
        raise FileNotFoundError("ssh-keygen não encontrado (OpenSSH do sistema)")
    return exe


def verificar_assinatura(arquivo, ancora, identidade: str, dados: bytes | None = None) -> dict:
    """Assinatura `<arquivo>.sig` conferida contra a âncora, na identidade e no namespace da barreira. `dados`: os bytes
    da decisão que quem chama já leu e conferiu; o `ssh-keygen` confere esses bytes, e a assinatura é lida uma vez só
    (cópia numa pasta temporária): trocar os arquivos no meio não muda o que é conferido (revisão independente da 1.6.0)."""
    arquivo = Path(arquivo)
    sig = Path(str(arquivo) + ".sig")
    try:
        bruto_sig = sig.read_bytes() if sig.is_file() else None
    except OSError:
        bruto_sig = None
    if bruto_sig is None:
        return {"ok": False, "motivo": "assinatura ausente"}
    dados = arquivo.read_bytes() if dados is None else dados
    res = {"ok": False, "sha256_assinatura": sha256_bytes(bruto_sig)}
    try:
        campos = _campos_da_assinatura(bruto_sig)
    except ValueError:
        return {**res, "motivo": "assinatura ilegível"}
    res.update(impressao_digital=campos["impressao_digital"], namespace=campos["namespace"])
    if campos["namespace"] != NAMESPACE:
        return {**res, "motivo": f"assinatura feita em outro namespace ({campos['namespace']}), não em {NAMESPACE}"}
    donos = [linha for linha in ler_ancora(ancora) if linha["impressao_digital"] == campos["impressao_digital"]]
    if not donos:
        return {**res, "motivo": "assinatura de uma chave que não está na âncora"}
    if not any(fnmatch.fnmatchcase(identidade, p) for linha in donos for p in linha["principais"]):
        return {**res, "motivo": f"o assinante da decisão ({identidade}) não é o dono da chave na âncora"}
    exe = ssh_keygen()
    with tempfile.TemporaryDirectory(prefix="fundacao-assinatura-") as pasta:
        copia = Path(pasta) / "decisao.sig"
        copia.write_bytes(bruto_sig)
        r = subprocess.run([exe, "-Y", "verify", "-f", str(ancora), "-I", identidade, "-n", NAMESPACE,
                            "-s", str(copia)], input=dados, capture_output=True, timeout=30)
    res.update(ssh_keygen=exe, ssh_keygen_do_sistema=exe == ssh_keygen_do_sistema(),
               saida=(r.stdout + r.stderr).decode("utf-8", "replace").strip())
    if r.returncode != 0:
        return {**res, "motivo": "assinatura não confere com o conteúdo da decisão (ou a âncora não a aceita)"}
    return {**res, "ok": True, "motivo": "assinatura válida"}


def _dentro(caminho: Path, base: Path) -> bool:
    try:
        caminho.relative_to(base)
        return True
    except ValueError:
        return False


def verificar_decisao(arquivo, pasta_projeto, ancora, politica: dict | None = None) -> dict:
    """Confere esquema, forma canônica, projeto, entrega inalterada e assinatura. Não altera nada. Tipo que a
    `politica` (de `carregar_politica`) dispensa vale sem assinatura — `forca: sem-assinatura`, lógica da política;
    sem `politica`, todo tipo exige. Assinatura presente é sempre conferida: inválida nunca é ignorada."""
    arquivo, pasta = Path(arquivo).resolve(), Path(pasta_projeto).resolve()
    res = {"arquivo": str(arquivo), "valida": False}
    if not _dentro(arquivo, pasta / "decisoes"):
        return {**res, "motivo": "decisão fora de decisoes/ do projeto"}
    try:
        bruto = arquivo.read_bytes()
    except OSError:
        return {**res, "motivo": "decisão ausente ou ilegível"}
    res["sha256_decisao"] = sha256_bytes(bruto)
    try:
        d = json.loads(bruto.decode("utf-8"))
    except ValueError:
        return {**res, "motivo": "decisão ilegível"}
    entrega = d.get("entrega") if isinstance(d, dict) else None
    faltam = [k for k in CAMPOS if k not in d] if isinstance(d, dict) else list(CAMPOS)
    textos = [k for k in CAMPOS if k != "entrega"]  # campos de texto: vão à trilha, ao banco e ao ssh-keygen
    if (faltam or d.get("schema_version") != SCHEMA or d.get("namespace") != NAMESPACE or d.get("tipo") not in TIPOS
            or not all(isinstance(d.get(k), str) for k in textos)
            or not isinstance(entrega, dict) or not all(isinstance(entrega.get(k), str) for k in ("caminho", "sha256"))):
        return {**res, "motivo": "decisão fora do esquema", "faltam": faltam}
    res.update({k: d[k] for k in ("tipo", "decisao_id", "task_id", "assinante", "entrega")})
    if canonico(d) != bruto:
        return {**res, "motivo": "decisão fora da forma canônica"}
    if d["project_id"] != pasta.name:
        return {**res, "motivo": "decisão de outro projeto"}
    alvo = (pasta / entrega["caminho"]).resolve()
    if not _dentro(alvo, pasta / "outputs"):
        return {**res, "motivo": "entrega fora de outputs/ do projeto"}
    if not alvo.is_file() or sha256_arquivo(alvo) != entrega["sha256"]:
        return {**res, "motivo": "entrega ausente ou alterada depois da decisão"}
    res["exige_assinatura"] = exige_assinatura(politica, d["tipo"])
    if not Path(str(arquivo) + ".sig").is_file():
        if res["exige_assinatura"]:
            return {**res, "motivo": "assinatura ausente"}
        return {**res, "valida": True, "forca": "sem-assinatura",
                "motivo": "a política não exige assinatura neste tipo: vale a identidade de quem registra"}
    if ancora is None or not Path(ancora).is_file():
        return {**res, "motivo": "âncora ausente"}
    res["assinatura"] = verificar_assinatura(arquivo, ancora, d["assinante"], dados=bruto)
    if not res["assinatura"]["ok"]:
        return {**res, "motivo": res["assinatura"]["motivo"]}
    return {**res, "valida": True, "forca": "assinatura", "motivo": "decisão assinada pelo titular e entrega inalterada"}


# ------------------------------------------------------------------ sondagem da âncora
def _direitos_windows(caminho: Path, direitos) -> dict:
    """Pede cada direito ao abrir o arquivo ou a pasta e fecha na hora, sem alterar nada. True = concedido."""
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    invalido = wintypes.HANDLE(-1).value
    out = {}
    for nome, acesso in direitos:
        # OPEN_EXISTING; FILE_FLAG_BACKUP_SEMANTICS para abrir pasta
        h = k32.CreateFileW(str(caminho), acesso, 0x7, None, 3, 0x02000000, None)
        if h != invalido:
            k32.CloseHandle(h)
        out[nome] = h != invalido
    return out


def _dono_windows(caminho: Path) -> str | None:
    literal = str(caminho).replace("'", "''")
    r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", f"(Get-Acl -LiteralPath '{literal}').Owner"],
                       capture_output=True, text=True, errors="replace", timeout=60)
    return r.stdout.strip() or None


# Direitos pedidos a cada ponto do caminho da âncora (`_direitos_windows`): quem os tem consegue alterá-la, apagá-la ou
# pôr outra no mesmo caminho — renomeando uma pasta (DELETE nela ou DELETE_CHILD na de cima) ou mudando permissões.
_NO_ARQUIVO = (("WRITE_DAC", 0x00040000), ("WRITE_OWNER", 0x00080000), ("DELETE", 0x00010000),
               ("GENERIC_WRITE", 0x40000000))
_NA_PASTA_DA_ANCORA = (("WRITE_DAC", 0x00040000), ("WRITE_OWNER", 0x00080000), ("DELETE", 0x00010000),
                       ("ADD_FILE", 0x0002), ("ADD_SUBDIRECTORY", 0x0004), ("DELETE_CHILD", 0x0040))
_NAS_PASTAS_ACIMA = (("WRITE_DAC", 0x00040000), ("WRITE_OWNER", 0x00080000), ("DELETE", 0x00010000),
                     ("DELETE_CHILD", 0x0040))


def _sondas_de_escrita(ancora: Path) -> tuple[bool, bool]:
    """(abre a âncora para escrita, cria arquivo na pasta dela), sem alterar nada: abrir para escrita sem escrever não
    muda o arquivo, e o arquivo-sonda criado ao lado é apagado na hora."""
    try:
        with open(ancora, "r+b"):
            pass
        abre = True
    except PermissionError:
        abre = False
    sonda = ancora.parent / f"sonda-executor-{uuid.uuid4().hex[:8]}.tmp"
    try:
        fd = os.open(sonda, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        os.remove(sonda)
        cria = True
    except PermissionError:
        cria = False
    return abre, cria


def _e_ligacao(caminho: Path) -> bool:
    """Link simbólico, junção ou outro ponto de nova análise: troca o destino do caminho sem mexer na âncora."""
    try:
        st = os.lstat(caminho)
    except OSError:
        return False
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & 0x400)  # REPARSE_POINT


def conferir_ancora(ancora) -> dict:
    """Sondagem: a âncora existe, é legível e ESTE processo não consegue alterá-la, criar arquivo ao lado nem pôr outra
    no mesmo caminho. Cada ponto do caminho, do arquivo até a raiz do disco, é conferido: nenhum é ligação e, no Windows,
    esta conta não tem nele os direitos de alterar, apagar ou renomear, nem de mudar permissões ou dono (sondagem da
    pasta acima: achado da sessão do preparo do host, 2026-10-21). Nada é alterado: os direitos são pedidos ao abrir e
    fechados na hora. O dono do arquivo troca as permissões sem UAC (observado na fundação de referência em
    2026-10-20, quando o arquivo nasceu com o usuário como dono e a sondagem só de escrita deu "protegida")."""
    ancora = Path(ancora).absolute()  # sem resolver: uma ligação no caminho é justamente o que se procura
    out = {"ancora": str(ancora), "existe": ancora.is_file()}
    if not out["existe"]:
        return {**out, "protegida": False, "motivo": "âncora ausente"}
    out["linhas"] = ler_ancora(ancora)
    out["abre_para_escrita"], out["cria_arquivo_na_pasta"] = _sondas_de_escrita(ancora)
    problemas = ([f"abrir {ancora} para escrita"] if out["abre_para_escrita"] else []) + (
        [f"criar arquivo em {ancora.parent}"] if out["cria_arquivo_na_pasta"] else [])
    out["cadeia"] = []
    for posicao, item in enumerate((ancora, *ancora.parents)):
        entrada = {"caminho": str(item), "ligacao": _e_ligacao(item)}
        if entrada["ligacao"]:
            problemas.append(f"ligação no caminho da âncora: {item}")
        if os.name == "nt":
            pedidos = _NO_ARQUIVO if posicao == 0 else _NA_PASTA_DA_ANCORA if posicao == 1 else _NAS_PASTAS_ACIMA
            entrada["direitos"] = _direitos_windows(item, pedidos)
            problemas += [f"{nome} em {item}" for nome, concedido in entrada["direitos"].items() if concedido]
        out["cadeia"].append(entrada)
    if os.name == "nt":
        out["dono"] = _dono_windows(ancora)
        out["direitos_no_arquivo"], out["direitos_na_pasta"] = out["cadeia"][0]["direitos"], out["cadeia"][1]["direitos"]
        r = subprocess.run(["icacls", str(ancora.parent)], capture_output=True, text=True, errors="replace", timeout=30)
        out["icacls_pasta"] = [linha.strip() for linha in r.stdout.splitlines() if linha.strip()][:8]
    else:
        out["aviso"] = ("dono e direitos de segurança (da âncora e das pastas acima) só são conferidos no Windows; "
                        "rode a sondagem também lá")
    out["protegida"] = not problemas
    out["motivo"] = "âncora protegida" if not problemas else "este processo consegue: " + "; ".join(problemas[:6])
    return out


# ------------------------------------------------------------------ comando para o titular
def no_windows() -> bool:
    return os.name == "nt"


def em_wsl() -> bool:
    """Linux do WSL (variável da distribuição ou kernel que se identifica como Microsoft)."""
    if no_windows():
        return False
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return False


def shell_padrao() -> str:
    """A chave do titular e a âncora ficam no Windows: ele assina no PowerShell também quando a sessão roda no WSL."""
    return "powershell" if no_windows() or em_wsl() else "bash"


def _barras(caminho) -> str:
    return str(caminho).replace(chr(92), "/")


def caminho_windows(caminho) -> str:
    """Caminho para o PowerShell: `/mnt/e/x` vira `E:` + `x` com barras invertidas; caminho do Windows fica igual;
    outro caminho do WSL vira o caminho de rede `wsl.localhost/<distribuição>/...` (sem a distribuição, recusa)."""
    s = _barras(caminho)
    m = re.match(r"^/mnt/([a-zA-Z])(/.*)?$", s)
    if m:
        return str(PureWindowsPath(m.group(1).upper() + ":" + (m.group(2) or "/")))
    if re.match(r"^[a-zA-Z]:/", s) or s.startswith("//"):
        return str(PureWindowsPath(s))
    distro = os.environ.get("WSL_DISTRO_NAME", "").strip()
    if s.startswith("/") and distro:
        return str(PureWindowsPath("//wsl.localhost/" + distro + s))
    raise DecisaoInvalida("caminho sem equivalente no Windows: gere o comando para o bash (--shell bash)",
                          caminho=str(caminho))


def caminho_wsl(caminho) -> str:
    """Caminho para o bash do WSL: `E:` + `x` vira `/mnt/e/x`; o caminho de rede do WSL volta a ser o do Linux;
    caminho POSIX fica igual."""
    s = _barras(caminho)
    m = re.match(r"^([a-zA-Z]):(/.*)?$", s)
    if m:
        return "/mnt/" + m.group(1).lower() + (m.group(2) or "/")
    m = re.match(r"^//wsl(?:\.localhost|\$)/[^/]+(/.*)?$", s, re.IGNORECASE)
    if m:
        return m.group(1) or "/"
    if s.startswith("/"):
        return s
    raise DecisaoInvalida("caminho sem equivalente no bash do WSL", caminho=str(caminho))


def _aspas_powershell(texto: str) -> str:
    return "'" + texto.replace("'", "''") + "'"


def _aspas_bash(texto: str) -> str:
    return "'" + texto.replace("'", "'" + chr(92) + "''") + "'"


def comando_para_o_titular(decisao, *, assinante: str, ancora, shell: str | None = None, chave=None) -> dict:
    """Comandos prontos para copiar, no shell em que o titular vai rodar (references/comunicacao-leigo.md §3):
    `assinar` pede a senha da chave e grava `<decisão>.sig`; `conferir` repete `ssh-keygen -Y verify` contra a
    âncora, sem depender do kit. O ssh-keygen vai pelo caminho do sistema. `chave` só para ensaio: o padrão é a chave
    do titular em ~/.ssh/fundacao_titular."""
    shell = shell or shell_padrao()
    if shell not in SHELLS:
        raise DecisaoInvalida("shell deve ser um de " + ", ".join(SHELLS), shell=shell)
    if not re.match(r"^[A-Za-z0-9._@-]+$", str(assinante)):
        raise DecisaoInvalida("assinante com caractere fora de [A-Za-z0-9._@-]", assinante=assinante)
    proibidos = ("\n", "\r", "\0") + (('"', "%") if shell == "powershell" else ())
    if any(c in str(t) for t in (decisao, ancora, chave or "") for c in proibidos):
        raise DecisaoInvalida(f"caminho com caractere que quebraria o comando no {shell}: use uma pasta sem ele")
    if shell == "powershell":
        dec, anc = caminho_windows(decisao), caminho_windows(ancora)
        exe = (ssh_keygen_do_sistema() if no_windows() else None) or SSH_KEYGEN_WINDOWS
        barra = chr(92)
        f_chave = (_aspas_powershell(caminho_windows(chave)) if chave
                   else '"$env:USERPROFILE' + barra + ".ssh" + barra + CHAVE_DO_TITULAR + '"')
        assinar = f"& {_aspas_powershell(exe)} -Y sign -f {f_chave} -n {NAMESPACE} {_aspas_powershell(dec)}"
        # O PowerShell não tem redirecionamento de entrada (`<`): a conferência passa pelo cmd.
        interno = f'"{exe}" -Y verify -f "{anc}" -I {assinante} -n {NAMESPACE} -s "{dec}.sig" < "{dec}"'
        return {"shell": shell, "onde_abrir": "PowerShell comum do Windows (não precisa ser administrador)",
                "assinar": assinar, "esperado_ao_assinar": f"pede a senha da chave e termina com: Write signature to {dec}.sig",
                "conferir": "cmd /c " + _aspas_powershell(interno),
                "esperado_ao_conferir": f'Good "{NAMESPACE}" signature for {assinante}'}
    dec, anc = caminho_wsl(decisao), caminho_wsl(ancora)
    exe = "/usr/bin/ssh-keygen"
    f_chave = _aspas_bash(caminho_wsl(chave)) if chave else '"$HOME/.ssh/' + CHAVE_DO_TITULAR + '"'
    return {"shell": shell, "onde_abrir": "terminal do Linux (no WSL: o terminal do Ubuntu)",
            "assinar": f"{exe} -Y sign -f {f_chave} -n {NAMESPACE} {_aspas_bash(dec)}",
            "esperado_ao_assinar": f"pede a senha da chave e termina com: Write signature to {dec}.sig",
            "conferir": (f"{exe} -Y verify -f {_aspas_bash(anc)} -I {assinante} -n {NAMESPACE} "
                         f"-s {_aspas_bash(dec + '.sig')} < {_aspas_bash(dec)}"),
            "esperado_ao_conferir": f'Good "{NAMESPACE}" signature for {assinante}'}


# ------------------------------------------------------------------ âncora desta máquina e política
def ancora_padrao() -> Path | None:
    """A âncora no lugar fixo desta máquina, se existir."""
    for candidata in ANCORAS_PADRAO:
        if Path(candidata).is_file():
            return Path(candidata)
    return None


def _mesmo_arquivo(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def resolver_ancora(pedida=None) -> Path | None:
    """Âncora que confere as decisões. Com a âncora padrão presente, só ela vale: outra, criada por quem opera a
    fundação, aceitaria uma chave qualquer. Sem a padrão (laboratório, outro sistema), a informada, ou nenhuma."""
    padrao = ancora_padrao()
    if padrao is None:
        return Path(pedida) if pedida else None
    if pedida and not _mesmo_arquivo(Path(pedida), padrao):
        raise DecisaoInvalida("nesta máquina vale só a âncora padrão; outra âncora não confere decisões",
                              ancora_padrao=str(padrao))
    return padrao


def politica_padrao() -> dict:
    return {"schema_version": SCHEMA_POLITICA, "tipos": {t: {"exige_assinatura": True} for t in TIPOS}}


def _validar_politica(dados) -> None:
    onde = f"(registry/{POLITICA})"
    if not isinstance(dados, dict) or dados.get("schema_version") != SCHEMA_POLITICA:
        raise DecisaoInvalida(f"política de decisões com schema_version desconhecido {onde}")
    extras = sorted(set(dados) - {"schema_version", "descricao", "tipos"})
    if extras:
        raise DecisaoInvalida(f"campos desconhecidos na política de decisões {onde}", campos=extras)
    tipos = dados.get("tipos", {})
    if not isinstance(tipos, dict):
        raise DecisaoInvalida(f"`tipos` da política de decisões precisa ser um mapa {onde}")
    for tipo, regra in tipos.items():
        if tipo not in TIPOS:
            raise DecisaoInvalida(f"tipo desconhecido na política de decisões {onde}", tipo=tipo)
        if not isinstance(regra, dict) or set(regra) != {"exige_assinatura"} or not isinstance(
                regra["exige_assinatura"], bool):
            raise DecisaoInvalida(f'regra da política de decisões: só {{"exige_assinatura": true|false}} {onde}',
                                  tipo=tipo)


def carregar_politica(raiz) -> dict:
    """Política de `registry/politica-decisoes.json`; sem o arquivo, todos os tipos exigem assinatura. Inválida:
    DecisaoInvalida. Numa máquina com a âncora padrão ela é o piso: dispensa de assinatura vira aviso, sem efeito."""
    efetiva = politica_padrao()
    arq = Path(raiz) / "registry" / POLITICA
    origem, sha = f"padrão do kit (sem registry/{POLITICA})", None
    if arq.is_file():
        bruto = arq.read_bytes()
        origem, sha = f"registry/{POLITICA}", sha256_bytes(bruto)
        try:
            dados = json.loads(bruto.decode("utf-8"))
        except ValueError:
            raise DecisaoInvalida(f"política de decisões ilegível (registry/{POLITICA})") from None
        _validar_politica(dados)
        for tipo, regra in dados.get("tipos", {}).items():
            efetiva["tipos"][tipo]["exige_assinatura"] = regra["exige_assinatura"]
    avisos = []
    padrao = ancora_padrao()
    dispensados = [t for t in TIPOS if not efetiva["tipos"][t]["exige_assinatura"]]
    if padrao is not None and dispensados:
        for tipo in dispensados:
            efetiva["tipos"][tipo]["exige_assinatura"] = True
        avisos.append(f"nesta máquina existe a âncora padrão ({padrao}): a política não dispensa assinatura em "
                      f"{', '.join(dispensados)} (piso da barreira)")
    return {**efetiva, "origem": origem, "sha256": sha, "avisos": avisos,
            "ancora_padrao": str(padrao) if padrao is not None else None}


def exige_assinatura(politica: dict | None, tipo: str) -> bool:
    if politica is None:
        return True
    return bool(politica["tipos"].get(tipo, {}).get("exige_assinatura", True))


def resumo_politica(politica: dict) -> dict:
    return {"origem": politica["origem"], "sha256": politica["sha256"], "avisos": politica["avisos"],
            "exige_assinatura": {t: exige_assinatura(politica, t) for t in TIPOS}}


# ------------------------------------------------------------------ preparar e registrar
def pasta_da_decisao(raiz, arquivo) -> tuple[str, Path]:
    """Projeto e caminho resolvido de uma decisão, que precisa estar em `projects/<projeto>/decisoes/` desta raiz."""
    alvo = Path(arquivo)
    alvo = (alvo if alvo.is_absolute() else Path.cwd() / alvo).resolve()
    try:
        partes = alvo.relative_to(projects_dir(raiz).resolve()).parts
    except ValueError:
        partes = ()
    if len(partes) < 3 or partes[1] != "decisoes":
        raise ValidationError("a decisão precisa estar em projects/<projeto>/decisoes/ desta raiz", arquivo=str(arquivo))
    return partes[0], alvo


def preparar_decisao(raiz, con, principal: Principal, *, projeto: str, tarefa: str, entrega: str, tipo: str,
                     motivo: str, decisao_id: str | None = None, ancora=None, politica: dict | None = None,
                     shell: str | None = None) -> dict:
    """Grava `decisoes/<id>.json` (JSON canônico com o SHA-256 da entrega exata, assinante = identidade do lançador)
    e devolve o comando do titular. Exige escrita no projeto; a tarefa precisa ser DESTE projeto (alheia responde
    como inexistente) e a entrega estar em `outputs/`. Não sobrescreve decisão existente."""
    pasta = project_root(raiz, con, principal, projeto, action="write")
    Coordinator(raiz, con, principal, projeto).get_task(tarefa)
    alvo = contained(pasta / "outputs", pasta / entrega, within=pasta)
    if not alvo.is_file():
        raise NotFound("entrega inexistente em outputs/ do projeto", entrega=str(entrega))
    if decisao_id is None:  # o padrão tem resolução de segundo: outra decisão no mesmo segundo ganha sufixo
        base = f"dec-{tipo}-{time.strftime('%Y%m%dT%H%M%S')}"
        decisao_id, n = base, 1
        while (pasta / "decisoes" / f"{decisao_id}.json").exists():
            n += 1
            decisao_id = f"{base}-{n}"
    d = montar_decisao(projeto=projeto, tarefa=tarefa, entrega_rel=alvo.relative_to(pasta).as_posix(),
                       entrega_sha256=sha256_arquivo(alvo), tipo=tipo, motivo=motivo, assinante=principal.principal_id,
                       decisao_id=decisao_id, agora=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    destino = contained(pasta / "decisoes", pasta / "decisoes" / f"{decisao_id}.json", within=pasta)
    if destino.exists():
        raise AlreadyExists("decisão já existe; nada foi alterado (não sobrescrevo)", decisao_id=decisao_id)
    titular = comando_para_o_titular(destino, assinante=principal.principal_id, shell=shell,
                                     ancora=ancora or ANCORAS_PADRAO[0])
    bruto = canonico(d)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "xb") as arq:  # "x": recusa se outra execução criou o arquivo no intervalo
        arq.write(bruto)
    events.emit(con, "decisao_preparada", project_id=projeto, subject=principal.principal_id, task_id=tarefa,
                payload={"decisao_id": decisao_id, "tipo": tipo, "sha256_decisao": sha256_bytes(bruto),
                         "sha256_entrega": d["entrega"]["sha256"]})
    exige = exige_assinatura(politica, tipo)
    registrar = f'python -m fundacao decisao registrar --arquivo "{destino}"'
    out = {"decisao": str(destino), "decisao_id": decisao_id, "sha256_decisao": sha256_bytes(bruto), "tipo": tipo,
           "task_id": tarefa, "entrega": d["entrega"], "assinatura_exigida": exige, "para_o_titular": titular,
           "proximo_passo": (f"o titular assina com o comando de para_o_titular; depois: {registrar}" if exige else
                             f"sem assinatura nesta fundação (política): {registrar}, por quem pode aprovar")}
    avisos = []
    if ancora is None:
        avisos.append("âncora ausente nesta máquina: a assinatura só pode ser conferida depois que o titular a criar")
    elif not any(fnmatch.fnmatchcase(principal.principal_id, p) for linha in ler_ancora(ancora)
                 for p in linha["principais"]):
        avisos.append(f"a identidade {principal.principal_id} não está na âncora: a assinatura seria recusada")
    return {**out, "avisos": avisos} if avisos else out


def ler_decisao(arquivo) -> dict:
    """Decisão como objeto JSON; outra coisa (ilegível, lista, número) é DecisaoInvalida, pelo contrato da CLI."""
    try:
        d = json.loads(Path(arquivo).read_text(encoding="utf-8"))
    except ValueError:
        d = None
    if not isinstance(d, dict):
        raise DecisaoInvalida("decisão ilegível ou fora do esquema", arquivo=str(arquivo))
    return d


def ler_registro(registro) -> list[dict]:
    """Linhas de `registro.jsonl`. Linha que não é objeto JSON: DecisaoInvalida (não se pula: sumiria com uma decisão)."""
    reg = Path(registro)
    if not reg.is_file():
        return []
    linhas = []
    for numero, bruta in enumerate(reg.read_text(encoding="utf-8").splitlines(), 1):
        if not bruta.strip():
            continue
        try:
            linha = json.loads(bruta)
        except ValueError:
            linha = None
        if not isinstance(linha, dict):
            raise DecisaoInvalida("registro de decisões com linha fora do formato", registro=str(reg), linha=numero)
        linhas.append(linha)
    return linhas


def decisao_vigente(registro, task_id: str) -> dict | None:
    """Última decisão registrada da tarefa (linhas de `registro.jsonl`), ou None."""
    da_tarefa = [linha for linha in ler_registro(registro) if linha.get("task_id") == task_id]
    return da_tarefa[-1] if da_tarefa else None


def registros_na_trilha(con, project_id: str, task_id: str | None = None) -> list[dict]:
    """Decisões registradas segundo a trilha de eventos do banco, em ordem (cópia do registro fora da pasta do
    projeto, onde quem opera o projeto escreve)."""
    sql = "SELECT payload_json FROM event WHERE kind IN (?, ?) AND project_id = ?"
    params = [EVENTO_ASSINADA, EVENTO_SEM_ASSINATURA, project_id]
    if task_id is not None:
        sql += " AND task_id = ?"
        params.append(task_id)
    return [json.loads(row["payload_json"]) for row in con.execute(sql + " ORDER BY seq", params)]


def registrar_decisao(con, principal: Principal, pasta_projeto, verificacao: dict, *, agora: str | None = None) -> dict:
    """Grava a decisão VÁLIDA (resultado de `verificar_decisao`) na trilha de eventos e em `decisoes/registro.jsonl`,
    com os campos da ferramenta da fundação. Idempotente pelo SHA-256 da decisão: com as duas cópias, "já
    registrada"; faltando uma (queda no meio), completa só a que falta. Tipo que a política dispensa de assinatura
    vale só registrado por quem pode aprovar no projeto e é o próprio assinante."""
    if not verificacao.get("valida"):
        raise DecisaoInvalida("decisão inválida não se registra: " + str(verificacao.get("motivo")))
    pasta = Path(pasta_projeto)
    projeto = pasta.name
    policy = Policy(con)
    policy.require(principal, "write", resource_project(projeto))
    sem_assinatura = verificacao.get("forca") == "sem-assinatura"
    if sem_assinatura:
        policy.require(principal, "approve", resource_project(projeto))
        if verificacao.get("assinante") != principal.principal_id:
            raise AccessDenied("decisão sem assinatura vale só registrada pelo próprio assinante",
                               action="approve", resource=resource_project(projeto))
    sha = verificacao["sha256_decisao"]
    reg = pasta / "decisoes" / REGISTRO
    no_registro = any(linha.get("sha256_decisao") == sha for linha in ler_registro(reg))
    na_trilha = any(p.get("sha256_decisao") == sha for p in registros_na_trilha(con, projeto))
    if no_registro and na_trilha:
        return {"registro": "já registrada", "registro_arquivo": str(reg)}
    assinatura = verificacao.get("assinatura") or {}
    linha = {k: verificacao[k] for k in ("decisao_id", "tipo", "task_id", "sha256_decisao", "entrega")}
    linha.update(impressao_digital=assinatura.get("impressao_digital"),
                 sha256_assinatura=assinatura.get("sha256_assinatura"),
                 registrado_em=agora or time.strftime("%Y-%m-%dT%H:%M:%S%z"), registrado_por=principal.principal_id)
    if sem_assinatura:
        linha["forca"] = "sem-assinatura"
    if not na_trilha:
        events.emit(con, EVENTO_SEM_ASSINATURA if sem_assinatura else EVENTO_ASSINADA, project_id=projeto,
                    subject=principal.principal_id, task_id=verificacao["task_id"],
                    payload={k: linha[k] for k in ("decisao_id", "tipo", "sha256_decisao", "sha256_assinatura",
                                                   "impressao_digital")})
    if not no_registro:
        reg.parent.mkdir(parents=True, exist_ok=True)
        with open(reg, "a", encoding="utf-8", newline="\n") as arq:
            arq.write(json.dumps(linha, ensure_ascii=False, sort_keys=True) + "\n")
    return {"registro": "registrada agora", "registro_arquivo": str(reg), "linha": linha}


# ------------------------------------------------------------------ concluir a tarefa
_TRILHA_NAO_CONFERIDA = object()


def apto_a_concluir(r: dict, vigente: dict | None, vigente_na_trilha=_TRILHA_NAO_CONFERIDA) -> str | None:
    """Motivo de recusa, ou None. `r`: resultado de `verificar_decisao`; `vigente`: última decisão da tarefa no
    registro do projeto; `vigente_na_trilha`: SHA-256 da última na trilha de eventos, ou None se a trilha não tem
    nenhuma — recusa: o registro fica na pasta do projeto, que quem opera o projeto altera (revisão independente da
    1.6.0). Sem o argumento, só o registro é conferido (quem confere a trilha à parte; `concluir_tarefa` sempre passa)."""
    if not r.get("valida"):
        return f"decisão inválida: {r.get('motivo')}"
    if r.get("tipo") != "aceite":
        return "só um aceite conclui a tarefa"
    if vigente is None or vigente.get("sha256_decisao") != r["sha256_decisao"]:
        return "o aceite precisa estar registrado e ser a decisão mais recente da tarefa"
    if vigente_na_trilha is _TRILHA_NAO_CONFERIDA:
        return None
    if vigente_na_trilha is None:
        return "o aceite precisa estar registrado também na trilha de eventos (rode decisao registrar)"
    if vigente_na_trilha != r["sha256_decisao"]:
        return "o registro do projeto e a trilha de eventos divergem sobre a decisão mais recente da tarefa"
    return None


def concluir_tarefa(raiz, con, principal: Principal, arquivo, *, ancora, politica: dict | None = None,
                    projeto: str | None = None) -> dict:
    """Conclui a tarefa com o aceite VÁLIDO sobre a entrega exata, registrado e mais recente da tarefa (no registro do
    projeto e na trilha). Registra uma execução de uma etapa que repete a conferência na hora de gravar; a tarefa passa
    a `succeeded`. Repetir devolve a mesma execução. Recusa: `concluida: false` com o motivo, e nada muda."""
    do_arquivo, arquivo = pasta_da_decisao(raiz, arquivo)
    if projeto is not None and projeto != do_arquivo:
        raise ValidationError("a decisão é de outro projeto", projeto=projeto)
    pasta = project_root(raiz, con, principal, do_arquivo, action="write")

    def recusa(v: dict) -> str | None:
        trilha = registros_na_trilha(con, do_arquivo, v.get("task_id"))
        return apto_a_concluir(v, decisao_vigente(pasta / "decisoes" / REGISTRO, v.get("task_id")),
                               trilha[-1].get("sha256_decisao") if trilha else None)

    r = verificar_decisao(arquivo, pasta, ancora, politica)
    motivo = recusa(r)
    if motivo:
        return {"concluida": False, "motivo": motivo, "decisao_id": r.get("decisao_id"), "task_id": r.get("task_id")}
    coord = Coordinator(raiz, con, principal, do_arquivo)
    coord.get_task(r["task_id"])  # tarefa deste projeto (alheia responde como inexistente)

    def conferir_aceite(ctx):
        # Repete a conferência dentro da etapa: o que vale é o estado no momento da gravação.
        de_novo = verificar_decisao(arquivo, pasta, ancora, politica)
        if recusa(de_novo):
            raise PermanentError("o aceite deixou de valer durante a etapa")
        assinatura = de_novo.get("assinatura") or {}
        return canonico({k: de_novo[k] for k in ("decisao_id", "tipo", "task_id", "sha256_decisao", "entrega")}
                        | {"impressao_digital": assinatura.get("impressao_digital"),
                           "sha256_assinatura": assinatura.get("sha256_assinatura")})

    run_id = coord.start_run(r["task_id"], FLUXO_ACEITE, r["decisao_id"], [StepDef(ETAPA_ACEITE, max_attempts=1)],
                             Budget(max_calls=0))
    final = coord.run(run_id, {ETAPA_ACEITE: conferir_aceite})
    tarefa = coord.get_task(r["task_id"])
    return {"concluida": tarefa["state"] == "succeeded", "run_id": run_id, "run_state": final["state"],
            "task_id": tarefa["task_id"], "task_state": tarefa["state"], "decisao_id": r["decisao_id"],
            "forca": r.get("forca")}
