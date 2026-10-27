"""Comando que o titular cola no próprio terminal para assinar e conferir uma decisão (references/comunicacao-leigo.md
§3), no shell em que ele vai rodar: no PowerShell, caminhos do Windows; no bash do WSL, `/mnt/<letra>/...`; e cada
caminho entre aspas que o shell não fecha antes da hora (avaliação E11, F-01). Saiu de decisoes.py na 1.7.4 (teto de
tamanho: divisão por responsabilidade); decisoes.py reexporta os nomes de sempre."""

from __future__ import annotations

import os
import re
from pathlib import Path, PureWindowsPath

SHELLS = ("powershell", "bash")


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
    from .decisoes import DecisaoInvalida  # tardio: decisoes importa este módulo
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
    from .decisoes import DecisaoInvalida  # tardio: decisoes importa este módulo
    raise DecisaoInvalida("caminho sem equivalente no bash do WSL", caminho=str(caminho))


# O PowerShell trata como aspa simples também as tipográficas U+2018 a U+201B, e como aspa dupla as U+201C a U+201E
# (avaliação E11, F-01): dentro da cadeia entre aspas simples, cada uma das cinco se dobra, como o apóstrofo ASCII.
ASPAS_SIMPLES_POWERSHELL = ("'",) + tuple(chr(c) for c in (0x2018, 0x2019, 0x201A, 0x201B))
ASPAS_DUPLAS_POWERSHELL = ('"',) + tuple(chr(c) for c in (0x201C, 0x201D, 0x201E))


def _aspas_powershell(texto: str) -> str:
    return "'" + "".join(c + c if c in ASPAS_SIMPLES_POWERSHELL else c for c in texto) + "'"


def _aspas_bash(texto: str) -> str:
    return "'" + texto.replace("'", "'" + chr(92) + "''") + "'"


def comando_para_o_titular(decisao, *, assinante: str, ancora, shell: str | None = None, chave=None,
                          namespace: str | None = None) -> dict:
    """Comandos prontos para copiar, no shell em que o titular vai rodar (references/comunicacao-leigo.md §3):
    `assinar` pede a senha da chave e grava `<decisão>.sig`; `conferir` repete `ssh-keygen -Y verify` contra a
    âncora, sem depender do kit. O ssh-keygen vai pelo caminho do sistema. `chave` só para ensaio: o padrão é a chave
    do titular em ~/.ssh/fundacao_titular."""
    from .decisoes import (CHAVE_DO_TITULAR, NAMESPACE, SSH_KEYGEN_WINDOWS,  # tardio: decisoes importa este módulo
                           DecisaoInvalida, ssh_keygen_do_sistema)
    NAMESPACE = namespace or NAMESPACE
    if NAMESPACE not in {"fundacao-decisao", "fundacao-copia"}:
        raise DecisaoInvalida("namespace de assinatura não suportado")
    shell = shell or shell_padrao()
    if shell not in SHELLS:
        raise DecisaoInvalida("shell deve ser um de " + ", ".join(SHELLS), shell=shell)
    if not re.fullmatch(r"[A-Za-z0-9._@-]+", str(assinante)):  # `$` aceitaria uma quebra de linha no fim
        raise DecisaoInvalida("assinante com caractere fora de [A-Za-z0-9._@-]", assinante=assinante)
    proibidos = ("\n", "\r", "\0") + ((*ASPAS_DUPLAS_POWERSHELL, "%") if shell == "powershell" else ())
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
