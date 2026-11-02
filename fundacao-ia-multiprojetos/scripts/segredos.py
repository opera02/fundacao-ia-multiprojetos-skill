#!/usr/bin/env python3
"""Conferência de segredo sem mostrar valores (1.7.10; DESENHO-1.7.10 §5.2; MELHORIAS-1.7.10, itens 0.7 e 0.8).

  python segredos.py conferir ALVO [--saida RELATORIO.json] [--teto-bytes N] [--incluir-pasta-ignorada NOME ...]

ALVO é uma pasta ou um arquivo. Para cada arquivo de texto, procura indícios de segredo e dá um veredito por arquivo
(`sem-indicio`, `indicio-forte` ou `indicio-fraco`) com o detector, a linha e o nome da chave quando houver; NUNCA o
valor, um trecho dele, o tamanho dele, um hash dele ou o texto da linha.

Detectores fortes: chave privada (PEM, OpenSSH, PGP, PuTTY), chave de acesso da AWS, token do GitHub, token e webhook
do Slack, chave da OpenAI e da Anthropic, chave do Stripe (sk_live_/rk_live_), chave de API do Google (AIza) e token
do npm e do GitLab (glpat-) pelo prefixo, JWT, URL com usuário e senha, e atribuição de variável com nome de segredo
(senha, token, secret, api_key, chave de acesso, credencial...) a um valor literal de 4 caracteres ou mais (entre
aspas o valor pode ter espaço) (forte quando o valor mistura letras e dígitos ou tem entropia alta; fraco quando não).
Detectores fracos: alta entropia em atribuição a qualquer nome e valor solto de cara de token num arquivo de até 3
linhas (como um `setup_token`). Valor de exemplo (`changeme`, `<...>`, `${VAR}`, `xxxx`, `your_...`) não é indício:
só é contado em `exemplos`.

"sem indício" NÃO é prova de que não há segredo: os detectores têm falso negativo (formato desconhecido, valor partido
em linhas, cifrado ou codificado, arquivo binário). O relatório diz isso, e a decisão de liberar a leitura de um
arquivo (por exemplo, a A1 do Automaton) tem de citá-lo.

Não segue ligação (vai para o relatório como `ligacao`, sem leitura); arquivo com vínculo físico (o outro nome pode
estar fora da pasta), binário (byte nulo no começo) ou acima do teto (padrão 5 MB) é pulado e contado; as pastas
reconstruíveis (`node_modules`, `.venv`...) e o `.git` são puladas e contadas — do `.git` só o `config`, o
`FETCH_HEAD` e o `logs/HEAD` são conferidos (URL de remoto ou credencial). Uma pasta pulada deixa o relatório
incompleto (`completo` falso, código 1): ela pode esconder segredo, e a decisão de liberar a leitura tem de
considerá-la. Quem roda lê o conteúdo: a conferência dos segredos importados é do titular, no terminal dele; a IA lê
só o relatório.

Código 0: tudo examinado (nada pulado) e nenhum indício; 1: algum indício, ou algo não examinado — pasta pulada,
binário, acima do teto, vínculo físico, ligação ou ilegível (o relatório diz o quê); 2: uso incorreto ou alvo
inexistente.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import stat
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ESQUEMA = "fundacao.segredos/1"
TETO_BYTES = 5_000_000
TETO_ITENS = 100_000
TETO_ACHADOS = 200          # por arquivo; o resto só é contado
AMOSTRA_BINARIO = 8192
MIN_VALOR = 4               # valor literal mínimo da atribuição com nome de segredo
MIN_ENTROPIA = 20           # valor mínimo para o detector de alta entropia
IGNORADAS = {"__pycache__", ".venv", "venv", "node_modules", ".mypy_cache", ".pytest_cache"}
SUBSTITUTA_DE_NOME = 0x20000000
AVISO = ("'sem indício' não é prova de que não há segredo. Falsos negativos conhecidos: valor partido em várias "
         "linhas; segredo cifrado, comprimido ou codificado (base64, hex); formato de chave desconhecido; conteúdo "
         "binário (não lido); nome fora do UTF-8 (não lido); arquivo acima do teto ou com vínculo físico (pulado); e "
         "o que está numa pasta pulada (reconstruível, ou o .git além de config, FETCH_HEAD e logs/HEAD). A decisão "
         "de liberar a leitura tem de citar este aviso. O relatório nunca traz valor, trecho, tamanho ou hash do que "
         "foi achado.")


def _rx(*partes: str, flags: int = 0) -> re.Pattern:
    """Expressão montada em pedaços: o texto deste fonte não casa a varredura de segredos da liberação."""
    return re.compile("".join(partes), flags)


FORTES = (  # (detector, expressão): só o nome do detector e a linha saem no relatório
    ("chave-privada", _rx(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE", r" KEY(?: BLOCK)?-----")),
    ("chave-putty", _rx(r"^PuTTY-User-Key-File-\d+:")),
    ("aws-chave-de-acesso", _rx(r"(?<![A-Z0-9])(?:A3T[A-Z0-9]|AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA)",
                                r"[A-Z0-9]{16}(?![A-Z0-9])")),
    ("github-token", _rx(r"(?<![A-Za-z0-9_])(?:gh[pousr]", r"_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})")),
    ("slack-token", _rx(r"(?<![A-Za-z0-9])xox[abposr]", r"-[A-Za-z0-9-]{10,}")),
    ("slack-webhook", _rx(r"hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]{8,}")),
    ("anthropic-chave", _rx(r"(?<![A-Za-z0-9_-])sk-", r"ant-[A-Za-z0-9_-]{20,}")),
    ("openai-chave", _rx(r"(?<![A-Za-z0-9_-])sk-", r"(?!ant-)(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{20,}")),
    ("jwt", _rx(r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    ("stripe-chave", _rx(r"(?<![A-Za-z0-9_])(?:sk|rk)", r"_live_[A-Za-z0-9]{10,}")),
    ("google-api-chave", _rx(r"(?<![A-Za-z0-9_-])AI", r"za[A-Za-z0-9_-]{35}")),
    ("npm-token", _rx(r"(?<![A-Za-z0-9_])npm", r"_[A-Za-z0-9]{36,}")),
    ("gitlab-token", _rx(r"(?<![A-Za-z0-9_-])glpat", r"-[A-Za-z0-9_-]{20,}")),
)
URL_COM_SENHA = _rx(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s:/@'\"<>]+:(?P<valor>[^\s/@'\"<>]+)", r"@")
ATRIBUICAO = _rx(r"""(?:^|[\s{,;(\[])["']?(?P<nome>[A-Za-z_][A-Za-z0-9_.\-]{0,79})["']?\s*(?::=|=>|=|:)\s*""",
                 r"""(?:(?P<aspas>["'`])(?P<valor_citado>[^"'`\r\n]{1,512})(?P=aspas)|(?P<valor>[^\s"'`]{1,512}))""")
TOKEN_SOLTO = re.compile(r"^[A-Za-z0-9+/=_\-.~:]{16,512}$")
VALOR_DE_ENTROPIA = re.compile(r"^[A-Za-z0-9+/=_\-.~]+$")
UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
NOME_SEGURO = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]{0,63}$")
# Partes de nome de variável que indicam segredo (comparadas sem caixa, em qualquer lugar do nome).
NOMES_DE_SEGREDO = ("secret", "token", "passwd", "password", "senha", "api_key", "apikey", "api-key", "access_key",
                    "accesskey", "private_key", "privatekey", "client_secret", "credential", "chave_api",
                    "chave_secreta", "chave_privada", "auth_key", "authkey")
NOMES_DE_HASH = ("sha", "hash", "digest", "checksum", "integrity", "etag", "commit", "revision", "uuid", "guid")
EXEMPLOS = ("example", "exemplo", "changeme", "change_me", "change-me", "placeholder", "dummy", "ficticio",
            "fictício", "replace_me", "replaceme", "redacted", "your_", "your-", "seu_", "sua_", "<", ">", "${", "{{",
            "%(", "xxxx", "****", "....", "process.env", "os.environ", "getenv")
# Arquivos em que valor sem aspas é literal (configuração); no código-fonte, sem aspas é referência.
SUFIXOS_DE_CONFIGURACAO = {".env", ".ini", ".cfg", ".conf", ".properties", ".yaml", ".yml", ".toml", ".sh", ".bash",
                           ".zsh", ".ps1", ".bat", ".cmd", ".txt", ".log", ".envrc", ".npmrc", ".pypirc"}
NOMES_DE_CONFIGURACAO = {"config", ".netrc", "_netrc", ".pgpass", ".envrc", ".npmrc", ".pypirc", "credentials"}
TRAVAS = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "pipfile.lock", "cargo.lock",
          "composer.lock", "gemfile.lock", "go.sum", "uv.lock"}


def entropia(texto: str) -> float:
    """Entropia de Shannon por caractere."""
    if not texto:
        return 0.0
    n = len(texto)
    return -sum(c / n * math.log2(c / n) for c in Counter(texto).values())


def e_exemplo(valor: str) -> bool:
    v = valor.casefold()
    return v.startswith("$") or len(set(v)) <= 2 or any(x in v for x in EXEMPLOS)


def nome_de_segredo(nome: str) -> bool:
    n = nome.casefold()
    return n not in ("pwd", "oldpwd") and (any(x in n for x in NOMES_DE_SEGREDO)
                                           or "pwd" in re.split(r"[_.\-]", n))


def chave_segura(nome: str | None) -> str | None:
    """O nome da chave só sai no relatório se tiver cara de nome (curto, sem cara de token)."""
    if not nome or not NOME_SEGURO.match(nome) or any(rx.search(nome) for _, rx in FORTES):
        return None
    if len(nome) >= 20 and entropia(nome) >= 3.5 and any(c.isdigit() for c in nome):
        return None
    if (len(nome) >= 12 and entropia(nome) >= 3.0 and not any(c in "_.-" for c in nome)
            and any(c.isalpha() for c in nome) and any(c.isdigit() for c in nome)):
        return None
    return nome


def _forca_do_valor(valor: str) -> str:
    letras, digitos = any(c.isalpha() for c in valor), any(c.isdigit() for c in valor)
    return "forte" if (letras and digitos) or entropia(valor) >= 3.5 else "fraco"


def _entropia_alta(valor: str) -> bool:
    return (len(valor) >= MIN_ENTROPIA and bool(VALOR_DE_ENTROPIA.match(valor)) and not UUID.match(valor)
            and any(c.isalpha() for c in valor) and any(c.isdigit() for c in valor) and entropia(valor) >= 3.5)


def examinar_texto(texto: str, nome_arquivo: str) -> tuple[list[dict], int, int]:
    """(achados, exemplos, achados além do teto). Nenhum achado guarda valor nem trecho."""
    nome_n = nome_arquivo.casefold()
    configuracao = (Path(nome_n).suffix in SUFIXOS_DE_CONFIGURACAO or nome_n.startswith(".env")
                    or nome_n in NOMES_DE_CONFIGURACAO or "." not in nome_n)
    trava = nome_n in TRAVAS or nome_n.endswith(".lock")
    achados, vistos, exemplos, alem = [], set(), 0, 0

    def achar(detector: str, linha: int, chave: str | None, forca: str) -> None:
        nonlocal alem
        marca = (detector, linha, chave)
        if marca in vistos:
            return
        vistos.add(marca)
        if len(achados) >= TETO_ACHADOS:
            alem += 1
            return
        achados.append({"detector": detector, "linha": linha, "chave": chave_segura(chave), "forca": forca})

    linhas = texto.splitlines()
    for i, linha in enumerate(linhas, 1):
        for detector, rx in FORTES:
            if rx.search(linha):
                achar(detector, i, None, "forte")
        for m in URL_COM_SENHA.finditer(linha):
            if e_exemplo(m["valor"]):
                exemplos += 1
            else:
                achar("url-com-senha", i, None, "forte")
        for m in ATRIBUICAO.finditer(linha):
            nome = m["nome"]
            citado = m["aspas"] is not None
            valor = m["valor_citado"] if citado else m["valor"]
            if valor is None:
                continue
            if not (citado or configuracao) or valor.startswith(("//", "http:", "https:")):
                continue  # sem aspas no código é referência; URL tem detector próprio
            if nome_de_segredo(nome) and len(valor) >= MIN_VALOR:
                if e_exemplo(valor):
                    exemplos += 1
                else:
                    achar("atribuicao-de-segredo", i, nome, _forca_do_valor(valor))
            elif (not trava and _entropia_alta(valor) and not e_exemplo(valor)
                  and not any(x in nome.casefold() for x in NOMES_DE_HASH)):
                achar("alta-entropia", i, nome, "fraco")
    preenchidas = [(i, l.strip()) for i, l in enumerate(linhas, 1) if l.strip()]
    if 0 < len(preenchidas) <= 3:
        for i, linha in preenchidas:
            if (TOKEN_SOLTO.match(linha) and _entropia_alta(linha.replace(":", ""))
                    and not any(a["linha"] == i for a in achados)):
                achar("valor-solto", i, None, "fraco")
    return achados, exemplos, alem


def e_ligacao(st: os.stat_result) -> bool:
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_reparse_tag", 0) & SUBSTITUTA_DE_NOME)


def ler(caminho: Path, base_real: Path, teto: int) -> bytes | None:
    """O conteúdo (None se passar do teto), sem seguir ligação: confere, depois de abrir, que é o arquivo do lstat,
    com um nome só, e que resolve dentro da pasta conferida."""
    st = os.lstat(caminho)
    if e_ligacao(st) or not stat.S_ISREG(st.st_mode) or st.st_nlink > 1:
        raise PermissionError("trocado")
    fd = os.open(caminho, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_NONBLOCK", 0))
    try:
        aberto = os.fstat(fd)
        if (not stat.S_ISREG(aberto.st_mode) or aberto.st_nlink > 1
                or (aberto.st_dev, aberto.st_ino) != (st.st_dev, st.st_ino)
                or not Path(os.path.realpath(caminho)).is_relative_to(base_real)):
            raise PermissionError("trocado")
        partes, lidos = [], 0
        while bloco := os.read(fd, min(1 << 20, teto + 1 - lidos)):
            partes.append(bloco)
            lidos += len(bloco)
            if lidos > teto:
                return None
        return b"".join(partes)
    finally:
        os.close(fd)


def conferir_arquivo(caminho: Path, rel: str, base_real: Path, teto: int) -> dict:
    try:
        st = os.lstat(caminho)
        if e_ligacao(st):
            return {"caminho": rel, "veredito": "ligacao"}
        if st.st_nlink > 1:
            return {"caminho": rel, "veredito": "vinculo-fisico"}
        if st.st_size > teto:
            return {"caminho": rel, "veredito": "acima-do-teto"}
        dados = ler(caminho, base_real, teto)
    except OSError as exc:
        return {"caminho": rel, "veredito": "ilegivel", "motivo": type(exc).__name__}
    if dados is None:
        return {"caminho": rel, "veredito": "acima-do-teto"}
    if b"\x00" in dados[:AMOSTRA_BINARIO]:
        return {"caminho": rel, "veredito": "binario"}
    achados, exemplos, alem = examinar_texto(dados.decode("utf-8", errors="replace"), caminho.name)
    forcas = {a["forca"] for a in achados}
    veredito = "indicio-forte" if "forte" in forcas else "indicio-fraco" if achados else "sem-indicio"
    item = {"caminho": rel, "veredito": veredito, "achados": achados, "exemplos": exemplos}
    if alem:
        item["achados_alem_do_teto"] = alem
    return item


def conferir(alvo: Path, teto: int = TETO_BYTES, incluir_ignoradas=()) -> dict:
    """O relatório da pasta ou do arquivo `alvo` (que não pode ser ligação)."""
    ignoradas = IGNORADAS - set(incluir_ignoradas)
    arquivos, puladas, limites = [], [], set()
    st = os.lstat(alvo)
    if e_ligacao(st):
        raise ValueError(f"o alvo é uma ligação, que não é seguida: {alvo}")
    if stat.S_ISREG(st.st_mode):
        arquivos.append(conferir_arquivo(alvo, alvo.name, Path(os.path.realpath(alvo.parent)), teto))
    elif stat.S_ISDIR(st.st_mode):
        base_real, vistos = Path(os.path.realpath(alvo)), 0
        pendentes = [(alvo, "")]
        while pendentes and not limites:
            pasta, rel_pasta = pendentes.pop()
            try:
                with os.scandir(pasta) as it:
                    entradas = sorted(it, key=lambda e: e.name, reverse=True)
            except OSError as exc:
                arquivos.append({"caminho": rel_pasta or ".", "veredito": "ilegivel", "motivo": type(exc).__name__})
                continue
            for e in entradas:
                vistos += 1
                if vistos > TETO_ITENS:
                    limites.add("itens")
                    break
                rel = f"{rel_pasta}/{e.name}" if rel_pasta else e.name
                try:
                    rel.encode("utf-8")
                except UnicodeEncodeError:
                    arquivos.append({"caminho": ascii(rel), "veredito": "ilegivel", "motivo": "nome fora do UTF-8"})
                    continue
                try:
                    st_e = os.lstat(e.path)
                except OSError as exc:
                    arquivos.append({"caminho": rel, "veredito": "ilegivel", "motivo": type(exc).__name__})
                    continue
                if e_ligacao(st_e):
                    arquivos.append({"caminho": rel, "veredito": "ligacao"})
                elif stat.S_ISDIR(st_e.st_mode) and e.name.casefold() == ".git":
                    puladas.append({"caminho": rel, "motivo": "pasta do Git: só config, FETCH_HEAD e logs/HEAD são "
                                                              "conferidos"})
                    for sub_git in ("config", "FETCH_HEAD", "logs/HEAD"):
                        alvo_git = Path(e.path).joinpath(*sub_git.split("/"))
                        try:
                            if stat.S_ISREG(os.lstat(alvo_git).st_mode):
                                arquivos.append(conferir_arquivo(alvo_git, f"{rel}/{sub_git}", base_real, teto))
                        except OSError:
                            pass
                elif stat.S_ISDIR(st_e.st_mode) and e.name in ignoradas:
                    puladas.append({"caminho": rel, "motivo": "pasta reconstruível (--incluir-pasta-ignorada a "
                                                              "confere)"})
                elif stat.S_ISDIR(st_e.st_mode):
                    pendentes.append((Path(e.path), rel))
                elif stat.S_ISREG(st_e.st_mode):
                    arquivos.append(conferir_arquivo(Path(e.path), rel, base_real, teto))
                else:
                    arquivos.append({"caminho": rel, "veredito": "especial"})
    else:
        raise ValueError(f"o alvo não é pasta nem arquivo comum: {alvo}")
    arquivos.sort(key=lambda a: a["caminho"])
    resumo = dict(sorted(Counter(a["veredito"] for a in arquivos).items()))
    resumo["pastas_puladas"] = len(puladas)
    nao_examinados = sum(n for v, n in resumo.items() if v in ("binario", "acima-do-teto", "vinculo-fisico",
                                                                "ilegivel", "ligacao", "especial"))
    return {"schema_version": ESQUEMA, "alvo": str(alvo), "criado_em": datetime.now(timezone.utc).isoformat(),
            "completo": not limites and nao_examinados == 0 and not puladas, "limites_atingidos": sorted(limites),
            "resumo": resumo, "arquivos": arquivos, "pastas_puladas": sorted(puladas, key=lambda p: p["caminho"]),
            "tetos": {"bytes_por_arquivo": teto, "itens": TETO_ITENS, "achados_por_arquivo": TETO_ACHADOS},
            "aviso": AVISO}


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("conferir", help="veredito por arquivo, sem mostrar valores")
    c.add_argument("alvo", type=Path)
    c.add_argument("--saida", type=Path, help="grava o relatório JSON também neste arquivo")
    c.add_argument("--teto-bytes", type=int, default=TETO_BYTES, help="arquivo maior que isto é pulado e contado")
    c.add_argument("--incluir-pasta-ignorada", action="append", default=[],
                   help="confere também esta pasta reconstruível (ex.: .venv)")
    args = ap.parse_args(argv)
    if args.teto_bytes <= 0:
        print(json.dumps({"erro": "--teto-bytes tem de ser positivo"}, ensure_ascii=False), file=sys.stderr)
        return 2
    try:
        rel = conferir(args.alvo, args.teto_bytes, args.incluir_pasta_ignorada)
    except (OSError, ValueError) as exc:
        motivo = str(exc) if isinstance(exc, ValueError) else f"alvo inexistente ou ilegível: {type(exc).__name__}"
        print(json.dumps({"erro": motivo}, ensure_ascii=False), file=sys.stderr)
        return 2
    texto = json.dumps(rel, ensure_ascii=False, indent=1)
    if args.saida:
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        args.saida.write_bytes((texto + "\n").encode("utf-8"))
    print(texto)
    indicio = any(a["veredito"].startswith("indicio") for a in rel["arquivos"])
    return 0 if rel["completo"] and not indicio else 1


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
