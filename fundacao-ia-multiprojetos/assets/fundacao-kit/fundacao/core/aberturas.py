"""Ficha de aberturas do projeto: a que vale, a numeração e o comando fixo do titular (1.7.10; contratos do lote 2, §5;
DESENHO-1.7.10 §3; crítica do desenho: "ficha vencida, ausente ou recusada fecha tudo, sem voltar à anterior").

`vigente(raiz, projeto, area)` diz o que vale para o projeto sem abrir o banco e sem exigir identidade (o preparo do
host e o porteiro a chamam direto). Lê SÓ a pasta `area` — no Ubuntu, a área do titular de dono root
(`/etc/fundacao-ia/projetos/<p>/ficha`); no Windows, a caixa de entrada da raiz (`.claude/projetos/<p>/ficha`, não
autoritativa) —, toma a MAIOR versão presente (`ficha-v<N>.json`) e só a aceita com a assinatura `ssh-keygen -Y` no
namespace `fundacao-abertura`, de uma chave da âncora `allowed_signers` cuja linha permite esse namespace, conferida
pelo caminho das decisões (core/decisoes.verificar_assinatura, ssh-keygen do sistema); e ainda inteira nos tetos
(core/aberturas_regras.py), na forma canônica, do mesmo projeto, com a versão do nome e não vencida. Se a maior não
vale, NÃO volta à anterior, que pode ser mais aberta: tudo fechado, com o motivo. Uma chave da âncora da 1.7.9
restrita a `fundacao-decisao` não abre nada: o motivo manda atualizar a âncora (passo do titular, com UAC). Contra
apagar a mais nova onde a sessão grava, quem guarda a maior versão já instalada é a área root (preparo do host); a
`raiz` entra no contrato e nada é lido dela aqui. O disco (listar, ler, criar) é o de core/aberturas_disco.py: no
POSIX, pela pasta aberta, sem seguir ligação.

A assinatura é só da ferramenta fixa do titular, nunca de comando montado pela sessão: `comando_do_titular`
(core/aberturas_comando.py, reexportado aqui) mostra a forma fixa dela, só com raiz, projeto e versão, na CÓPIA
PROTEGIDA da ferramenta, e diz onde rodá-la sem o perfil de um shell (a caixa Executar, Win+R).

Honestidade (contratos, §0): com a raiz em /mnt/e o sandbox não confinou os comandos nas sondas de 31/10/2026; lá o
isolamento entre projetos é lógico até o canário passar. Nenhuma abertura vale sem o resultado do canário no checklist
do projeto, conferido pelo preparo do host: este módulo só diz se a ficha está assinada, inteira e em vigor.
"""

from __future__ import annotations

import hashlib
import os
import re
import struct
import subprocess
import tempfile
from datetime import date
from fnmatch import fnmatchcase
from pathlib import Path

from . import decisoes
from .aberturas_comando import (ESQUEMA_HASHES, FERRAMENTA_POSIX, FERRAMENTA_WINDOWS, PYTHON_POSIX,  # noqa: F401
                                REL_FERRAMENTA, comando_do_titular, python_da_copia_windows)  # (reexportados)
from .aberturas_disco import LeituraRecusada, Pasta
from .aberturas_regras import ID_PROJETO, NAMESPACE, TETO_FICHA, canonico, carregar, mostrar, validar
from .contracts import PathEscape

AREA_DO_TITULAR = "/etc/fundacao-ia/projetos/{projeto}/ficha"  # Ubuntu: dono root (contratos do lote 2, §6)
ROTULO_CAIXA = "caixa-de-entrada (não instalada)"
PARTES_DA_CAIXA = (".claude", "projetos")  # <raiz>/.claude/projetos/<p>/ficha/
RASCUNHOS = ("outputs", "aberturas")  # projects/<p>/outputs/aberturas/ficha-v<N>.json, gravados pelo preparar
VERSAO_RE = re.compile(r"ficha-v([1-9][0-9]{0,8})\.json")  # até aberturas_regras.VERSAO_MAXIMA
TETO_ASSINATURA = 16 * 1024
HONESTIDADE = ("Com a raiz em /mnt/e (WSL), o sandbox não confinou os comandos nas sondas de 31/10/2026: lá o "
               "isolamento entre projetos é lógico (regras, trava de projeto do kit, porteiro e hooks). Nenhuma abertura "
               "vale antes de o canário (scripts/ensaio_isolamento_wsl.py) passar no ambiente real e constar no "
               "checklist do projeto, nem sem esta ficha assinada pelo titular.")
_PRINCIPAL = re.compile(r"[A-Za-z0-9._@-]+")


def nome_da_ficha(versao: int) -> str:
    return f"ficha-v{int(versao)}.json"


def partes_da_caixa(projeto: str) -> tuple[str, ...]:
    return (*PARTES_DA_CAIXA, projeto, "ficha")


def caixa_de_entrada(raiz, projeto: str) -> Path:
    """`<raiz>/.claude/projetos/<p>/ficha/`: onde a ferramenta do titular grava a ficha assinada (espelho legível e
    caixa de entrada do preparo do host; não é a área que vale no Ubuntu)."""
    return Path(raiz).joinpath(*partes_da_caixa(projeto))


def area_padrao(raiz, projeto: str) -> tuple[Path, str | None]:
    """A área de `abertura vigente` sem `--area`: no Linux, a do titular, de dono root; no Windows, a caixa de entrada
    da raiz, com o rótulo de não instalada (contratos, §5)."""
    if os.name == "nt":
        return caixa_de_entrada(raiz, projeto), ROTULO_CAIXA
    return Path(AREA_DO_TITULAR.format(projeto=projeto)), None


def versoes(nomes) -> dict[int, str]:
    """{versão: nome} dos nomes `ficha-v<N>.json` (só pelo nome)."""
    return {int(m.group(1)): nome for nome in nomes if (m := VERSAO_RE.fullmatch(nome))}


def listar_versoes(pasta) -> dict[int, str]:
    """{versão: nome} das fichas da pasta, só pelo nome (nada é lido). Pasta ausente: {}. A pasta, ou um ponto do
    caminho dela, que seja ligação (ou que não seja pasta): PathEscape. Aberta da raiz do volume para baixo, sem
    seguir ligação (Pasta.absoluta)."""
    with Pasta.absoluta(pasta) as aberta:
        return versoes(aberta.nomes())


def namespace_permitido(padroes: list[str] | None, namespace: str) -> bool:
    """A lista `namespaces=` da linha da âncora (padrões do OpenSSH, com `!` de negação); sem a opção, todos."""
    if padroes is None:
        return True
    if any(p.startswith("!") and fnmatchcase(namespace, p[1:]) for p in padroes):
        return False
    return any(not p.startswith("!") and fnmatchcase(namespace, p) for p in padroes)


def conferir_assinatura(bruto: bytes, sig: bytes, ancora=None) -> dict:
    """A assinatura `sig` sobre os bytes `bruto`, no namespace fundacao-abertura, de uma chave da âncora cuja linha
    permite esse namespace, conferida pelo ssh-keygen do sistema (nenhum do PATH). Com a âncora padrão desta máquina
    presente, só ela vale (decisoes.resolver_ancora). Devolve ok e motivo; ok, também o assinante e a impressão."""
    try:
        ancora = decisoes.resolver_ancora(ancora)
    except decisoes.DecisaoInvalida as exc:
        return {"ok": False, "motivo": str(exc)}
    if ancora is None or not Path(ancora).is_file():
        return {"ok": False, "motivo": "âncora ausente nesta máquina: nenhuma assinatura confere"}
    try:
        campos = decisoes._campos_da_assinatura(sig)
    except (ValueError, IndexError, struct.error):
        return {"ok": False, "motivo": "assinatura ilegível"}
    if campos["namespace"] != NAMESPACE:
        return {"ok": False, "motivo": f"assinatura feita em outro namespace ({mostrar(campos['namespace'])}), não em "
                                       f"{NAMESPACE}: o aceite de uma entrega não abre nada"}
    linhas = [li for li in decisoes.ler_ancora(ancora) if li["impressao_digital"] == campos["impressao_digital"]]
    if not linhas:
        return {"ok": False, "motivo": "assinatura de uma chave que não está na âncora"}
    permitidas = [li for li in linhas if namespace_permitido(li["namespaces"], NAMESPACE)]
    if not permitidas:
        return {"ok": False, "motivo": f"a âncora limita esta chave a {','.join(linhas[0]['namespaces'] or [])} e não "
                                       f"inclui {NAMESPACE}: atualize a âncora (passo do titular, com UAC, no "
                                       "preparar-maquina.ps1)"}
    assinante = next((p for li in permitidas for p in li["principais"] if _PRINCIPAL.fullmatch(p)), None)
    if assinante is None:
        return {"ok": False, "motivo": "a linha da âncora desta chave não tem um principal sem curinga"}
    if not decisoes.ssh_keygen_do_sistema():
        return {"ok": False, "motivo": "OpenSSH do sistema ausente: nenhum verificador do PATH é aceito"}
    try:
        with tempfile.TemporaryDirectory(prefix="fundacao-abertura-") as pasta:
            alvo = Path(pasta) / "ficha.json"
            alvo.write_bytes(bruto)
            Path(str(alvo) + ".sig").write_bytes(sig)
            r = decisoes.verificar_assinatura(alvo, ancora, assinante, dados=bruto, namespace=NAMESPACE)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "motivo": f"a conferência não rodou ({exc.__class__.__name__})"}
    if not r.get("ok") or r.get("ssh_keygen_do_sistema") is not True:
        return {"ok": False, "motivo": r.get("motivo") or "assinatura não confere"}
    return {"ok": True, "motivo": "assinatura válida", "assinante": assinante,
            "impressao_digital": campos["impressao_digital"]}


def _resultado(projeto, area) -> dict:
    return {"projeto": projeto, "valida": False, "versao": None, "arquivo": None, "sha256": None, "sig_sha256": None,
            "ficha": None, "motivo_invalida": None, "area": str(area)}


def conferir_versao(area, versao: int, projeto: str, *, hoje: date | None = None, ancora=None) -> dict:
    """A ficha `ficha-v<versao>.json` da `area`, inteira: assinatura, tetos, projeto, versão, vigência e forma
    canônica. Mesmo formato de `vigente`. A listagem e as duas leituras usam a mesma pasta aberta."""
    res = _resultado(projeto, area)
    nome = nome_da_ficha(versao)
    res.update(versao=int(versao), arquivo=str(Path(area) / nome))

    def recusa(motivo: str) -> dict:
        return {**res, "motivo_invalida": f"ficha v{versao}: {motivo}; tudo fechado, sem voltar à versão anterior"}
    if not isinstance(projeto, str) or not ID_PROJETO.fullmatch(projeto) or "--" in projeto:
        return recusa("identificador de projeto inválido")
    try:
        with Pasta.absoluta(area) as aberta:
            presente = int(versao) in versoes(aberta.nomes())
            bruto = aberta.ler(nome, TETO_FICHA) if presente else None
            sig = aberta.ler(nome + ".sig", TETO_ASSINATURA) if presente else None
    except (PathEscape, LeituraRecusada) as exc:
        return recusa(str(exc))
    except OSError as exc:
        return recusa(f"área ilegível ({exc.__class__.__name__})")
    if bruto is None:
        return recusa("arquivo ausente")
    res["sha256"] = hashlib.sha256(bruto).hexdigest()
    if sig is None:
        return recusa("sem assinatura (.sig)")
    res["sig_sha256"] = hashlib.sha256(sig).hexdigest()
    conferida = conferir_assinatura(bruto, sig, ancora)
    if not conferida["ok"]:
        return recusa(conferida["motivo"])
    try:
        ficha = carregar(bruto)
    except ValueError as exc:
        return recusa(f"ficha ilegível ({exc})")
    erros = validar(ficha, projeto=projeto, hoje=hoje or date.today())["erros"]
    if erros:
        return recusa(f"{erros[0]['campo']}: {erros[0]['motivo']}" + (f" (e mais {len(erros) - 1})" if erros[1:] else ""))
    if ficha["versao"] != int(versao):
        return recusa("a versão escrita na ficha difere da do nome do arquivo")
    if canonico(ficha) != bruto:
        return recusa("fora da forma canônica")
    return {**res, "valida": True, "ficha": ficha}


def vigente(raiz, projeto: str, area, *, hoje: date | None = None, ancora=None) -> dict:
    """A ficha que vale para o projeto, lida só de `area` (obrigatória), sem banco e sem identidade: a de MAIOR versão,
    se ela valer; senão, tudo fechado (`valida` falso, `ficha` None e o motivo). `hoje` e `ancora`: para ensaio; a
    âncora padrão desta máquina, se existir, é a única que vale. Formato (contratos, §5): projeto, valida, versao,
    arquivo, sha256, sig_sha256, ficha, motivo_invalida e area."""
    res = _resultado(projeto, area)
    if not isinstance(projeto, str) or not ID_PROJETO.fullmatch(projeto) or "--" in projeto:
        return {**res, "motivo_invalida": "identificador de projeto inválido: tudo fechado"}
    try:
        presentes = listar_versoes(area)
    except PathEscape as exc:
        return {**res, "motivo_invalida": f"{exc}: tudo fechado"}
    except OSError as exc:
        return {**res, "motivo_invalida": f"área ilegível ({exc.__class__.__name__}): tudo fechado"}
    if not presentes:
        return {**res, "motivo_invalida": "nenhuma ficha assinada nesta área: tudo fechado"}
    return conferir_versao(area, max(presentes), projeto, hoje=hoje, ancora=ancora)


def proxima_versao(raiz, projeto: str, pasta_projeto) -> int:
    """1 + a maior versão vista nos rascunhos do projeto, na caixa de entrada e, no Linux, na área do titular (o
    preparo do host recusa instalar versão menor que a maior já instalada)."""
    vistas = [0]
    for base, partes in ((pasta_projeto, RASCUNHOS), (raiz, partes_da_caixa(projeto))):
        with Pasta(base, partes) as aberta:
            vistas += versoes(aberta.nomes())
    if os.name != "nt":
        vistas += listar_versoes(AREA_DO_TITULAR.format(projeto=projeto))
    return 1 + max(vistas)
