#!/usr/bin/env python3
"""Testes de caracterização ("golden master") para adaptar projetos existentes (Fluxo B).

Grava o comportamento ATUAL de um programa para entradas conhecidas e depois compara o
comportamento após a mudança: código de término, saída padrão e saída de erro INTEIRAS (por
SHA-256 e tamanho; o golden guarda só um trecho para leitura) e os EFEITOS de cada caso na pasta
de saída — arquivos escritos ou removidos por aquele caso, separados dos que já existiam antes
dele (um arquivo antigo esquecido na pasta não mascara um programa que parou de produzi-lo).

  gravar   --entradas "dir/*.json" --saida golden.json [--cwd DIR] [--pasta-saida DIR | --ensaio DIR]
           [--ignorar REGEX ...] [--timeout 30] -- programa arg1 {entrada} [{ensaio}] ...
  comparar --golden golden.json [--cwd DIR] [--pasta-saida DIR | --ensaio DIR] -- programa arg1 {entrada} ...

`{entrada}` é substituído pelo caminho de cada entrada. `--ensaio DIR`: pasta de ensaio criada
pela PRÓPRIA ferramenta (marca `.caracterizar-ensaio`); cada caso roda numa subpasta nova e vazia,
passada em `{ensaio}`. A ferramenta só limpa pasta com essa marca: pasta existente sem a marca
(ex.: do usuário) é recusada e nada é apagado. O comando é passado como lista (sem shell). Use
--ignorar para neutralizar campos voláteis (ex.: datas) antes da comparação.
Diferenças -> código 1; uso incorreto -> 2. Uma diferença pode ser regressão OU mudança
intencional: registre a decisão no plano de adaptação, não ajuste o golden silenciosamente.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

MARCA_ENSAIO = ".caracterizar-ensaio"
TRECHO_STDOUT, TRECHO_STDERR = 20000, 4000  # só para leitura; a comparação usa o hash do conteúdo inteiro


def norm(text: str, patterns: list[str]) -> str:
    text = text.replace("\r\n", "\n")
    for p in patterns:
        text = re.sub(p, "<IGNORADO>", text)
    return text


def sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def foto(pasta: Path | None) -> dict:
    """Estado da pasta: caminho relativo -> (sha256, mtime_ns). Pasta inexistente = vazia."""
    if not pasta or not pasta.exists():
        return {}
    out = {}
    for p in sorted(pasta.rglob("*")):
        if p.is_file() and p.name != MARCA_ENSAIO:
            out[p.relative_to(pasta).as_posix()] = (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
    return out


def efeitos(antes: dict, depois: dict) -> dict:
    """O que ESTE caso fez: arquivos escritos (criados ou regravados) com o hash final, e removidos."""
    escritos = {rel: h for rel, (h, mt) in depois.items() if rel not in antes or antes[rel] != (h, mt)}
    return {"escritos": dict(sorted(escritos.items())), "removidos": sorted(set(antes) - set(depois))}


def preparar_ensaio(pasta: Path) -> None:
    """Cria a pasta de ensaio com a marca, ou aceita a que a ferramenta já criou. Nunca outra."""
    if pasta.exists():
        if not (pasta / MARCA_ENSAIO).is_file():
            raise SystemExit(_erro(f"--ensaio {pasta} já existe e não foi criada por esta ferramenta (sem a marca "
                                   f"{MARCA_ENSAIO}): escolha uma pasta nova; nada foi apagado"))
        return
    pasta.mkdir(parents=True)
    (pasta / MARCA_ENSAIO).write_text(json.dumps({"criada_em": datetime.now(timezone.utc).isoformat(),
                                                  "por": "caracterizar.py"}), encoding="utf-8")


def _erro(msg: str) -> int:
    print(json.dumps({"erro": msg}, ensure_ascii=False), file=sys.stderr)
    return 2


def run_case(cmd: list[str], entrada: str, cwd: Path | None, out_dir: Path | None, patterns: list[str],
             timeout: int, ensaio: Path | None = None, indice: int = 0) -> dict:
    caso_dir = None
    if ensaio is not None:
        caso_dir = ensaio / f"caso-{indice:03d}"
        if caso_dir.exists():
            shutil.rmtree(caso_dir)  # só dentro da pasta de ensaio marcada
        caso_dir.mkdir()
    pasta_efeitos = caso_dir if caso_dir is not None else out_dir
    argv = [a.replace("{entrada}", entrada).replace("{ensaio}", str(caso_dir or "")) for a in cmd]
    antes = foto(pasta_efeitos)
    try:
        p = subprocess.run(argv, capture_output=True, cwd=str(cwd) if cwd else None, timeout=timeout)
        stdout = norm(p.stdout.decode("utf-8", "replace"), patterns)
        stderr = norm(p.stderr.decode("utf-8", "replace"), patterns)
        code = p.returncode
    except subprocess.TimeoutExpired:
        stdout, stderr, code = "", "TIMEOUT", "timeout"
    depois = foto(pasta_efeitos)
    return {"entrada": entrada, "codigo": code,
            "stdout_sha256": sha(stdout), "stdout_tamanho": len(stdout), "stdout": stdout[:TRECHO_STDOUT],
            "stderr_sha256": sha(stderr), "stderr_tamanho": len(stderr), "stderr": stderr[:TRECHO_STDERR],
            "efeitos": efeitos(antes, depois), "preexistentes": len(antes),
            "arquivos": {rel: h for rel, (h, _mt) in depois.items()}}  # foto final (só p/ golden do formato 1)


def comparar_caso(antes: dict, agora: dict) -> list[str]:
    if "stdout_sha256" not in antes:  # golden do formato 1: só os trechos e a foto da pasta
        campos = [("codigo", "codigo"), ("stdout", "stdout"), ("stderr", "stderr")]
        diverg = [k for k, _ in campos if agora[k] != antes.get(k)]
        if agora["arquivos"] != antes.get("arquivos", {}):
            diverg.append("arquivos")
        return diverg
    return [nome for nome, chave in (("codigo", "codigo"), ("stdout", "stdout_sha256"), ("stderr", "stderr_sha256"),
                                     ("efeitos", "efeitos")) if agora[chave] != antes.get(chave)]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # O comando vem depois de "--"; separar antes do argparse evita que as opções
    # sejam engolidas por um posicional do tipo REMAINDER.
    opts, cmd = (argv[:argv.index("--")], argv[argv.index("--") + 1:]) if "--" in argv else (argv, [])
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("acao", choices=["gravar", "comparar"])
    ap.add_argument("--entradas")
    ap.add_argument("--saida", type=Path)
    ap.add_argument("--golden", type=Path)
    ap.add_argument("--cwd", type=Path)
    pasta = ap.add_mutually_exclusive_group()
    pasta.add_argument("--pasta-saida", type=Path, help="pasta onde o programa grava (efeitos por caso)")
    pasta.add_argument("--ensaio", type=Path, help="pasta de ensaio criada e limpa pela ferramenta ({ensaio})")
    ap.add_argument("--ignorar", action="append", default=[])
    ap.add_argument("--timeout", type=int, default=30)
    args = ap.parse_args(opts)
    if not cmd:
        ap.error("informe o comando após --")
    if any("{ensaio}" in a for a in cmd) and not args.ensaio:
        ap.error("o comando usa {ensaio}: informe --ensaio <pasta nova>")
    if args.acao == "gravar" and (not args.entradas or not args.saida):
        ap.error("gravar exige --entradas e --saida")
    if args.acao == "comparar" and not args.golden:
        ap.error("comparar exige --golden")
    if args.ensaio:
        preparar_ensaio(args.ensaio)
    if args.acao == "gravar":
        files = sorted(glob.glob(args.entradas))
        if not files:
            ap.error("nenhuma entrada encontrada")
        cases = [run_case(cmd, f, args.cwd, args.pasta_saida, args.ignorar, args.timeout, args.ensaio, i)
                 for i, f in enumerate(files)]
        golden = {"schema_version": "fundacao.golden/2", "comando": cmd, "ignorar": args.ignorar,
                  "comparacao": "codigo, sha256 de stdout e stderr inteiros, efeitos por caso", "casos": cases}
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        args.saida.write_text(json.dumps(golden, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"casos_gravados": len(cases), "saida": str(args.saida)}, ensure_ascii=False))
        return 0
    golden = json.loads(args.golden.read_text(encoding="utf-8"))
    diffs = []
    for i, case in enumerate(golden["casos"]):
        now = run_case(cmd, case["entrada"], args.cwd, args.pasta_saida, golden.get("ignorar", []), args.timeout,
                       args.ensaio, i)
        changed = comparar_caso(case, now)
        if changed:
            mostrar = {"codigo": "codigo", "stdout": "stdout", "stderr": "stderr", "efeitos": "efeitos",
                       "arquivos": "arquivos"}
            diffs.append({"entrada": case["entrada"], "campos_divergentes": changed,
                          "antes": {k: case.get(mostrar[k]) for k in changed},
                          "depois": {k: now.get(mostrar[k]) for k in changed}})
    saida = {"casos": len(golden["casos"]), "divergencias": diffs}
    if golden.get("schema_version") != "fundacao.golden/2":
        saida["aviso"] = ("golden do formato 1: compara só os trechos gravados (20.000/4.000 caracteres) e a foto da "
                          "pasta; grave de novo para comparar as saídas inteiras e os efeitos por caso")
    print(json.dumps(saida, ensure_ascii=False, indent=2))
    return 1 if diffs else 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
