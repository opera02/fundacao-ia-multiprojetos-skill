#!/usr/bin/env python3
"""Medidor de gasto a partir das transcrições JSONL do Claude Code (1.7.11): só leitura, só biblioteca padrão.

  python medir_gasto.py <arquivo ou pasta> [<arquivo ou pasta> ...] [--saida <arquivo.json>]

Devolve um JSON com:
- `tokens`: entrada, saída, cache lido e cache criado, somados UMA vez por `message.id` (o host grava a mesma resposta
  em várias linhas, uma por bloco; somar por linha infla o total de 2,5 a 3 vezes). De várias linhas com o mesmo
  `message.id` vale a última com `usage` legível. Totais, por modelo e por arquivo (o arquivo é o da linha vencedora).
- `resultados_de_ferramenta`: tamanho, em caracteres, dos resultados de ferramenta, por nome da ferramenta (liga o
  `tool_use_id` ao nome do `tool_use`); para `Bash`, também por comando (só a primeira palavra, e a segunda de `gh`,
  `git` e `python`, quando são só letras: nunca argumento, caminho ou texto). Caracteres, não tokens: a razão de ~4
  caracteres por token é só uma ordem de grandeza.
- `nao_lido`: o que não deu para ler, em contagens (linha que não é JSON, linha grande demais, `usage` ausente ou
  malformado, resposta sem `message.id`, arquivo ausente ou ilegível, resultado de ferramenta sem nome). `usage`
  ausente ou malformado nunca vira zero: a resposta entra só em `nao_lido`.

Lê em fluxo, linha a linha (a linha acima de `LIMITE_LINHA` bytes é descartada e contada). Não imprime conteúdo de
mensagem: só números, nomes de ferramenta, nomes de modelo e o nome do arquivo (sem a pasta). Não procura transcrição
sozinho: só abre o que for nomeado; numa pasta, os `.jsonl` e `.output` dela, em qualquer profundidade.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

LIMITE_LINHA = 64 * 1024 * 1024
CAMPOS_USAGE = (
    ("input_tokens", "entrada"),
    ("output_tokens", "saida"),
    ("cache_read_input_tokens", "cache_lido"),
    ("cache_creation_input_tokens", "cache_criado"),
)
SUFIXOS = {".jsonl", ".output"}
_PALAVRA = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
_COM_SUBCOMANDO = {"gh", "git", "python", "python3", "pip", "npm", "cargo", "wsl", "docker"}
_VAZIO = {k: 0 for _, k in CAMPOS_USAGE}


def _nao_lido() -> dict:
    return {
        "arquivo_ausente_ou_ilegivel": 0,
        "linha_nao_json": 0,
        "linha_grande": 0,
        "resposta_sem_message_id": 0,
        "resposta_sem_usage_legivel": 0,
        "resultado_sem_tool_use_id": 0,
        "resultado_de_ferramenta_sem_nome": 0,
    }


def _linhas(caminho: Path):
    """Linhas do arquivo em fluxo; `None` no lugar da linha maior que o limite (o resto dela é descartado)."""
    with open(caminho, "rb") as f:
        while True:
            bruta = f.readline(LIMITE_LINHA + 1)
            if not bruta:
                return
            if len(bruta) > LIMITE_LINHA and not bruta.endswith(b"\n"):
                while True:
                    resto = f.readline(LIMITE_LINHA)
                    if not resto or resto.endswith(b"\n"):
                        break
                yield None
                continue
            yield bruta


def _usage(u) -> dict | None:
    """Os quatro contadores como inteiros, ou `None` se algum falta ou não é inteiro não negativo."""
    if not isinstance(u, dict):
        return None
    saida = {}
    for campo, chave in CAMPOS_USAGE:
        v = u.get(campo)
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            return None
        saida[chave] = v
    return saida


def _tamanho(conteudo) -> int:
    """Caracteres do resultado de ferramenta: texto direto ou a soma dos blocos de texto (imagem não conta)."""
    if isinstance(conteudo, str):
        return len(conteudo)
    total = 0
    if isinstance(conteudo, list):
        for b in conteudo:
            if isinstance(b, str):
                total += len(b)
            elif isinstance(b, dict) and isinstance(b.get("text"), str):
                total += len(b["text"])
    return total


_ASPAS = re.compile(r'"(?:\\.|[^"\\])*"' + r"|'[^']*'", re.S)
_CORTE = re.compile(r"&&|\|\||;|\||\n|\(|\)|`")
_PULA = re.compile(r"^(cd|pushd|popd|set|export|true|false|unset|source|\.|:)(\s|$)")
_ATRIB = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S*(\s+|$)")


def _comando(entrada) -> str:
    """Categoria segura de um comando do Bash: a primeira palavra do primeiro comando de fato (sem `cd`, `export` e
    atribuições de variável; sem o conteúdo de aspas) e, p/ ferramentas conhecidas, a segunda palavra se for só letras."""
    cmd = entrada.get("command") if isinstance(entrada, dict) else None
    if not isinstance(cmd, str):
        return "(sem comando)"
    cmd = _ASPAS.sub('""', cmd).replace("\\", "/")
    for trecho in _CORTE.split(cmd):
        trecho = trecho.strip()
        while _ATRIB.match(trecho):
            trecho = _ATRIB.sub("", trecho, count=1).strip()
        if not trecho or _PULA.match(trecho):
            continue
        partes = trecho.split()
        primeira = partes[0].rsplit("/", 1)[-1]
        if primeira.lower().endswith(".exe"):
            primeira = primeira[:-4]
        if not _PALAVRA.match(primeira):
            return "(outro)"
        if primeira in _COM_SUBCOMANDO and len(partes) > 1 and _PALAVRA.match(partes[1]):
            return f"{primeira} {partes[1]}"
        return primeira
    return "(vazio)"


def _somar(dest: dict, usage: dict) -> None:
    for k, v in usage.items():
        dest[k] = dest.get(k, 0) + v


def medir(caminhos: list[Path]) -> dict:
    nao_lido = _nao_lido()
    arquivos: list[Path] = []
    for c in caminhos:
        if c.is_dir():
            arquivos.extend(sorted(p for p in c.rglob("*") if p.is_file() and p.suffix.lower() in SUFIXOS))
        else:
            arquivos.append(c)

    respostas: dict[str, tuple[str, str, dict]] = {}  # message.id -> (modelo, arquivo, usage) da última linha legível
    resultados: dict[str, dict] = {}
    bash: dict[str, dict] = {}
    vistos_resultado: set[str] = set()
    sem_usage: set[str] = set()
    por_arquivo_info: list[dict] = []
    nomes_usados: dict[str, int] = {}

    for caminho in arquivos:
        base = caminho.name
        nomes_usados[base] = nomes_usados.get(base, 0) + 1
        rotulo = base if nomes_usados[base] == 1 else f"{base}#{nomes_usados[base]}"
        info = {"arquivo": rotulo, "linhas": 0}
        ferramentas: dict[str, tuple[str, str]] = {}  # tool_use_id -> (nome, categoria de comando)
        try:
            for bruta in _linhas(caminho):
                info["linhas"] += 1
                if bruta is None:
                    nao_lido["linha_grande"] += 1
                    continue
                if not bruta.strip():
                    continue
                try:
                    obj = json.loads(bruta)
                except (ValueError, UnicodeDecodeError, RecursionError):
                    nao_lido["linha_nao_json"] += 1
                    continue
                msg = obj.get("message") if isinstance(obj, dict) else None
                if not isinstance(msg, dict):
                    continue
                conteudo = msg.get("content")
                if obj.get("type") == "assistant":  # as linhas "api-request-*" repetem mensagens: não valem
                    if isinstance(conteudo, list):
                        for b in conteudo:
                            if isinstance(b, dict) and b.get("type") == "tool_use" and isinstance(b.get("id"), str):
                                nome = b.get("name") if isinstance(b.get("name"), str) else "(sem nome)"
                                ferramentas[b["id"]] = (nome, _comando(b.get("input")) if nome == "Bash" else "")
                    mid = msg.get("id")
                    if not isinstance(mid, str) or not mid:
                        nao_lido["resposta_sem_message_id"] += 1
                        continue
                    u = _usage(msg.get("usage"))
                    if u is None:
                        sem_usage.add(mid)
                        continue
                    modelo = msg.get("model") if isinstance(msg.get("model"), str) else "(sem modelo)"
                    respostas[mid] = (modelo, rotulo, u)
                elif obj.get("type") == "user" and isinstance(conteudo, list):
                    for b in conteudo:
                        if not (isinstance(b, dict) and b.get("type") == "tool_result"):
                            continue
                        tid = b.get("tool_use_id")
                        if not isinstance(tid, str) or not tid:
                            nao_lido["resultado_sem_tool_use_id"] += 1
                            continue
                        chave_unica = f"{rotulo}\0{tid}"
                        if chave_unica in vistos_resultado:
                            continue
                        vistos_resultado.add(chave_unica)
                        nome, cat = ferramentas.get(tid, (None, ""))
                        if nome is None:
                            nao_lido["resultado_de_ferramenta_sem_nome"] += 1
                            nome = "(sem nome)"
                        n = _tamanho(b.get("content"))
                        r = resultados.setdefault(nome, {"resultados": 0, "caracteres": 0, "maior": 0})
                        r["resultados"] += 1
                        r["caracteres"] += n
                        r["maior"] = max(r["maior"], n)
                        if nome == "Bash":
                            c = bash.setdefault(cat, {"resultados": 0, "caracteres": 0, "maior": 0})
                            c["resultados"] += 1
                            c["caracteres"] += n
                            c["maior"] = max(c["maior"], n)
        except OSError:
            nao_lido["arquivo_ausente_ou_ilegivel"] += 1
            info["erro"] = "ausente ou ilegível"
        por_arquivo_info.append(info)

    nao_lido["resposta_sem_usage_legivel"] = len(sem_usage - respostas.keys())
    total = dict(_VAZIO)
    por_modelo: dict[str, dict] = {}
    por_arquivo: dict[str, dict] = {i["arquivo"]: {**_VAZIO, "respostas": 0} for i in por_arquivo_info}
    for modelo, rotulo, u in respostas.values():
        _somar(total, u)
        m = por_modelo.setdefault(modelo, {**_VAZIO, "respostas": 0})
        _somar(m, u)
        m["respostas"] += 1
        a = por_arquivo[rotulo]
        _somar(a, u)
        a["respostas"] += 1

    caracteres = sum(r["caracteres"] for r in resultados.values())
    return {
        "arquivos": por_arquivo_info,
        "tokens": {
            "respostas_contadas": len(respostas),
            "total": total,
            "por_modelo": dict(sorted(por_modelo.items())),
            "por_arquivo": por_arquivo,
        },
        "resultados_de_ferramenta": {
            "caracteres_total": caracteres,
            "por_ferramenta": dict(sorted(resultados.items(), key=lambda kv: -kv[1]["caracteres"])),
            "bash_por_comando": dict(sorted(bash.items(), key=lambda kv: -kv[1]["caracteres"])),
        },
        "nao_lido": nao_lido,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Mede o gasto (tokens por message.id e tamanho dos resultados de ferramenta).")
    p.add_argument("caminhos", nargs="+", help="arquivos JSONL de transcrição ou pastas com eles")
    p.add_argument("--saida", help="grava o JSON neste arquivo (UTF-8) em vez de imprimir")
    a = p.parse_args(argv)
    texto = json.dumps(medir([Path(c) for c in a.caminhos]), ensure_ascii=False, indent=2) + "\n"
    if a.saida:
        Path(a.saida).write_bytes(texto.encode("utf-8"))
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(texto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
