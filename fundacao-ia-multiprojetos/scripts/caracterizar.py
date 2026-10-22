#!/usr/bin/env python3
"""Testes de caracterização ("golden master") para adaptar projetos existentes (Fluxo B).

Grava o comportamento ATUAL de um programa para entradas conhecidas e depois compara o
comportamento após a mudança: código de término, saída padrão e saída de erro INTEIRAS (por
SHA-256 e tamanho; o golden guarda só um trecho para leitura) e os EFEITOS de cada caso na pasta
de saída — arquivos escritos ou removidos por aquele caso, separados dos que já existiam antes
dele (um arquivo antigo esquecido na pasta não mascara um programa que parou de produzi-lo).

  plano    (os argumentos do gravar ou do comparar, sem --plano-aprovado) [--gravar-plano plano.json]
  gravar   --plano-aprovado SHA256 --entradas "dir/*.json" --saida golden.json [--copia DIR --manifesto M]
           [--cwd DIR] [--pasta-saida DIR | --ensaio DIR] [--ignorar REGEX ...] [--timeout 30]
           [--variavel NOME[=VALOR] ...] [--sem-isolamento "motivo"] -- programa arg1 {entrada} [{ensaio}] ...
  comparar --plano-aprovado SHA256 --golden golden.json (as mesmas opções) -- programa arg1 {entrada} ...

O programa é código importado: cada caso roda pelo lançador `execucao_isolada.py`, com o plano que
`plano` mostra — isolamento (bubblewrap no Linux/WSL; sem ele, recusa, salvo `--sem-isolamento` com o
motivo), programa e comando, cópia (só leitura) e SHA-256 do manifesto dela, entradas, pasta gravável,
ambiente, rede e limites (--timeout, --teto-saida-mb, --memoria-mb, --arquivo-mb, --processos) — e o
SHA-256 dele, com o texto da folha de decisões (`folha_do_plano.py`). `gravar` e `comparar` recalculam o
plano com os argumentos recebidos e só rodam se o hash for o aprovado [auditoria Codex Security da 1.7.6,
#1]. O hash prende o programa (ex.: o python3), não o script: `--copia` exige `--manifesto`, que prende a
cópia; sem cópia (só sem isolamento), o plano e a folha dizem que o código não está preso [revisão de
segurança da 1.7.7, R177-FB-02]; com ela, também, se a pasta de trabalho fica fora da cópia, se uma
variável pedida muda de onde o código é carregado ou se {entrada}/{ensaio} ficam no lugar do script
[segunda passada, R177B-B-02]. Programa, manifesto e cópia são conferidos antes e depois de cada caso:
divergência para a execução, e o golden não é gravado [R177B-B-03].
`{entrada}` é substituído pelo caminho de cada entrada (no bubblewrap, o absoluto, onde ela é montada).
`--ensaio DIR`: pasta de ensaio criada pela PRÓPRIA ferramenta (marca `.caracterizar-ensaio`); cada caso
roda numa subpasta nova e vazia, passada em `{ensaio}`. A ferramenta só limpa pasta com essa marca: pasta
existente sem a marca (ex.: do usuário) é recusada e nada é apagado. O comando é passado como lista (sem
shell). Use --ignorar para neutralizar campos voláteis (ex.: datas) antes da comparação.
Diferenças -> código 1; uso incorreto ou recusa -> 2. Uma diferença pode ser regressão OU mudança
intencional: registre a decisão no plano de adaptação, não ajuste o golden silenciosamente.
No timeout, o código fica `timeout`; acima do teto de saída, `saida_acima_do_teto` (a saída fica cortada
no teto). Nos dois, a saída parcial é guardada e comparada; golden gravado antes disso compara só código
e efeitos nos casos com timeout.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

MARCA_ENSAIO = ".caracterizar-ensaio"
TRECHO_STDOUT, TRECHO_STDERR = 20000, 4000  # só para leitura; a comparação usa o hash do conteúdo inteiro


def _carregar(nome: str):
    """Um script ao lado deste (o lançador e a folha), carregado pelo caminho, sem mexer no `sys.path`."""
    spec = importlib.util.spec_from_file_location(nome, Path(__file__).resolve().parent / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


EXEC = _carregar("execucao_isolada")
FOLHA = _carregar("folha_do_plano")


def norm(text: str, patterns: list[str]) -> str:
    text = text.replace("\r\n", "\n")
    for p in patterns:
        text = re.sub(p, "<IGNORADO>", text)
    return text


def sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def foto(pasta: Path | None) -> dict:
    """Estado da pasta: caminho relativo -> (sha256, mtime_ns). Pasta inexistente = vazia. Ligação (link simbólico
    ou junção) não é seguida: entra pelo destino escrito nela, sem ler o outro lado — quem grava na pasta é o
    programa importado [auditoria Codex Security da 1.7.6, #1]."""
    if not pasta or not pasta.is_dir():
        return {}
    out = {}
    for raiz, pastas, arquivos in os.walk(pasta):
        for nome in sorted(pastas + arquivos):
            p = Path(raiz) / nome
            st = os.lstat(p)
            rel = p.relative_to(pasta).as_posix()
            if stat.S_ISLNK(st.st_mode) or getattr(st, "st_reparse_tag", 0) & 0x20000000:  # junção e afins
                out[rel] = (sha(f"ligação -> {os.readlink(p)}"), st.st_mtime_ns)
                if nome in pastas:
                    pastas.remove(nome)  # o os.walk entraria na junção do Windows
            elif stat.S_ISREG(st.st_mode) and nome != MARCA_ENSAIO:
                h = hashlib.sha256()
                with open(p, "rb") as f:
                    for bloco in iter(lambda: f.read(1 << 20), b""):
                        h.update(bloco)
                out[rel] = (h.hexdigest(), st.st_mtime_ns)
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
             timeout: int, ensaio: Path | None = None, indice: int = 0, plano: dict | None = None, *,
             sem_isolamento: str | None = None) -> dict:
    """Um caso, pelo lançador, com o plano aprovado (`gravar` e `comparar` sempre o passam). Chamada direta da
    biblioteca sem plano só com `sem_isolamento="<motivo>"` explícito (programa fictício): sem isolamento, mas com
    ambiente mínimo, árvore contida e os limites padrão. Sem plano e sem motivo, recusa e nada roda [revisão de
    segurança da 1.7.7: antes, rodava sem isolamento por padrão]."""
    if plano is None:
        if not sem_isolamento:
            raise EXEC.Recusa("run_case sem plano: passe o plano aprovado (`caracterizar.py plano`) ou, só para "
                              "programa fictício, sem_isolamento=\"<motivo>\"; nada foi executado")
        plano = EXEC.montar_plano("caso", cmd, copia=None, manifesto=None, cwd=cwd, entradas=[], gravavel=None,
                                  limites=EXEC.limites(timeout), variaveis=[], sem_isolamento=sem_isolamento)
    caso_dir = None
    if ensaio is not None:
        caso_dir = ensaio / f"caso-{indice:03d}"
        if caso_dir.exists():
            shutil.rmtree(caso_dir)  # só dentro da pasta de ensaio marcada
        caso_dir.mkdir()
    pasta_efeitos = caso_dir if caso_dir is not None else out_dir
    isolado = plano["isolamento"] == "bwrap"
    if isolado and pasta_efeitos is not None:
        pasta_efeitos.mkdir(parents=True, exist_ok=True)  # o bubblewrap só monta pasta que existe
    no_caso = os.path.abspath(entrada) if isolado and entrada else entrada
    gravavel = os.path.abspath(pasta_efeitos) if isolado and pasta_efeitos is not None else None
    argv = [a.replace("{entrada}", no_caso).replace("{ensaio}", gravavel if isolado and caso_dir else str(caso_dir or ""))
            for a in cmd]
    antes = foto(pasta_efeitos)
    # A16: o que o programa escreveu antes do corte (prazo ou teto de saída) também é comportamento observado.
    r = EXEC.executar(plano, argv, entrada=no_caso if isolado and entrada else None, gravavel=gravavel)
    stdout = norm(r["stdout"].decode("utf-8", "replace"), patterns)
    stderr = norm(r["stderr"].decode("utf-8", "replace"), patterns)
    code = r["codigo"]
    depois = foto(pasta_efeitos)
    return {"entrada": entrada, "codigo": code,
            "stdout_sha256": sha(stdout), "stdout_tamanho": len(stdout), "stdout": stdout[:TRECHO_STDOUT],
            "stderr_sha256": sha(stderr), "stderr_tamanho": len(stderr), "stderr": stderr[:TRECHO_STDERR],
            "efeitos": efeitos(antes, depois), "preexistentes": len(antes),
            "arquivos": {rel: h for rel, (h, _mt) in depois.items()}}  # foto final (só p/ golden do formato 1)


def comparar_caso(antes: dict, agora: dict, timeout_sem_saida: bool = False) -> list[str]:
    """`timeout_sem_saida`: golden gravado quando o timeout descartava a saída (stdout vazio, stderr
    "TIMEOUT"); nesses casos stdout e stderr gravados não são o que o programa escreveu e ficam fora."""
    fora = {"stdout", "stderr"} if timeout_sem_saida and antes.get("codigo") == "timeout" else set()
    if "stdout_sha256" not in antes:  # golden do formato 1: só os trechos e a foto da pasta
        campos = [("codigo", "codigo"), ("stdout", "stdout"), ("stderr", "stderr")]
        diverg = [k for k, _ in campos if k not in fora and agora[k] != antes.get(k)]
        if agora["arquivos"] != antes.get("arquivos", {}):
            diverg.append("arquivos")
        return diverg
    return [nome for nome, chave in (("codigo", "codigo"), ("stdout", "stdout_sha256"), ("stderr", "stderr_sha256"),
                                     ("efeitos", "efeitos")) if nome not in fora and agora[chave] != antes.get(chave)]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # O comando vem depois de "--"; separar antes do argparse evita que as opções
    # sejam engolidas por um posicional do tipo REMAINDER.
    opts, cmd = (argv[:argv.index("--")], argv[argv.index("--") + 1:]) if "--" in argv else (argv, [])
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("acao", choices=["plano", "gravar", "comparar"])
    ap.add_argument("--entradas")
    ap.add_argument("--saida", type=Path)
    ap.add_argument("--golden", type=Path)
    ap.add_argument("--copia", type=Path, help="pasta da cópia do código (no isolamento, montada só leitura); exige "
                    "--manifesto")
    ap.add_argument("--manifesto", type=Path, help="manifesto da cópia (manifesto.py criar): prende o código que o "
                    "programa roda e é conferido antes e depois de cada caso")
    ap.add_argument("--cwd", type=Path, help="pasta de trabalho do programa (padrão: a cópia; fora dela, o código não "
                    "fica preso)")
    pasta = ap.add_mutually_exclusive_group()
    pasta.add_argument("--pasta-saida", type=Path, help="pasta onde o programa grava (efeitos por caso)")
    pasta.add_argument("--ensaio", type=Path, help="pasta de ensaio criada e limpa pela ferramenta ({ensaio})")
    ap.add_argument("--ignorar", action="append", default=[])
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--teto-saida-mb", type=int, default=32, help="teto de stdout e de stderr (cada um) por caso")
    ap.add_argument("--memoria-mb", type=int, default=4096)
    ap.add_argument("--arquivo-mb", type=int, default=512)
    ap.add_argument("--processos", type=int, default=256)
    ap.add_argument("--variavel", action="append", default=[], help="NOME (valor de quem chama) ou NOME=VALOR")
    ap.add_argument("--sem-isolamento", metavar="MOTIVO", help="sem sandbox: toda a autoridade da conta; motivo no plano")
    ap.add_argument("--plano-aprovado", metavar="SHA256", help="hash do plano aprovado (gravar e comparar)")
    ap.add_argument("--gravar-plano", type=Path, help="(plano) grava o plano e o hash neste arquivo")
    args = ap.parse_args(opts)
    if not cmd:
        ap.error("informe o comando após --")
    if any("{ensaio}" in a for a in cmd) and not args.ensaio:
        ap.error("o comando usa {ensaio}: informe --ensaio <pasta nova>")
    if args.acao == "plano" and bool(args.entradas) == bool(args.golden):
        ap.error("plano exige --entradas (plano do gravar) ou --golden (plano do comparar)")
    if args.acao == "gravar" and (not args.entradas or not args.saida):
        ap.error("gravar exige --entradas e --saida")
    if args.acao == "comparar" and not args.golden:
        ap.error("comparar exige --golden")
    if args.acao != "plano" and not args.plano_aprovado:
        return _erro("informe --plano-aprovado <sha256>, o hash do plano aprovado pelo titular (gere-o com "
                     "`caracterizar.py plano` e os mesmos argumentos); nada foi executado")
    acao = "gravar" if args.acao == "gravar" or (args.acao == "plano" and args.entradas) else "comparar"
    golden = json.loads(args.golden.read_text(encoding="utf-8")) if acao == "comparar" else None
    files = sorted(glob.glob(args.entradas)) if acao == "gravar" else [c["entrada"] for c in golden["casos"]]
    if acao == "gravar" and not files:
        ap.error("nenhuma entrada encontrada")
    gravavel = ("ensaio", args.ensaio) if args.ensaio else ("pasta-saida", args.pasta_saida) if args.pasta_saida else None
    try:
        plano = EXEC.montar_plano(acao, cmd, copia=args.copia, manifesto=args.manifesto, cwd=args.cwd, entradas=files,
                                  gravavel=gravavel, limites=EXEC.limites(args.timeout, args.teto_saida_mb,
                                                                          args.memoria_mb, args.arquivo_mb,
                                                                          args.processos),
                                  variaveis=args.variavel, sem_isolamento=args.sem_isolamento)
        if args.saida and gravavel and args.saida.resolve().is_relative_to(gravavel[1].resolve()):
            raise EXEC.Recusa("--saida dentro da pasta gravável: lá escreve o programa importado; grave o golden fora")
        EXEC.conferir(plano)  # programa, manifesto e cópia, antes de qualquer caso
    except (EXEC.Recusa, OSError) as exc:
        return _erro(f"{exc}; nada foi executado")
    sha_plano = EXEC.sha256_do_plano(plano)
    if args.acao == "plano":
        saida = {"sha256": sha_plano, "isolamento": plano["isolamento"],
                 "para_a_folha": FOLHA.para_a_folha(plano, sha_plano), "plano": plano}
        if args.gravar_plano:
            args.gravar_plano.parent.mkdir(parents=True, exist_ok=True)
            args.gravar_plano.write_text(json.dumps({"sha256": sha_plano, "plano": plano}, ensure_ascii=False, indent=2)
                                         + "\n", encoding="utf-8", newline="\n")
        print(json.dumps(saida, ensure_ascii=False, indent=2))
        return 0
    if args.plano_aprovado.strip().lower() != sha_plano:
        return _erro(f"o plano mudou desde a aprovação (aprovado {args.plano_aprovado}, agora {sha_plano}): programa, "
                     "comando, cópia, manifesto (ou o que a cópia tem fora dele), entradas, pastas, ambiente, rede ou "
                     "limites diferentes; nada foi executado. Mostre o plano novo (`caracterizar.py plano` com estes "
                     "argumentos) e peça novo aceite")
    if args.ensaio:
        preparar_ensaio(args.ensaio)
    try:
        return _executar(acao, args, cmd, plano, sha_plano, files, golden)
    except (EXEC.Recusa, OSError) as exc:  # a cópia mudou entre os casos, inclusive [R177B-B-03]
        return _erro(f"execução interrompida: {exc}; " + ("o golden não foi gravado" if acao == "gravar"
                                                          else "a comparação não terminou"))


def _executar(acao: str, args, cmd: list[str], plano: dict, sha_plano: str, files: list[str], golden: dict | None) -> int:
    if acao == "gravar":
        cases = [run_case(cmd, f, args.cwd, args.pasta_saida, args.ignorar, args.timeout, args.ensaio, i, plano)
                 for i, f in enumerate(files)]
        golden = {"schema_version": "fundacao.golden/2", "comando": cmd, "ignorar": args.ignorar,
                  "comparacao": "codigo, sha256 de stdout e stderr inteiros, efeitos por caso",
                  "saida_parcial_no_timeout": True, "plano_sha256": sha_plano, "isolamento": plano["isolamento"],
                  "casos": cases}
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        args.saida.write_text(json.dumps(golden, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"casos_gravados": len(cases), "saida": str(args.saida), "plano_sha256": sha_plano},
                         ensure_ascii=False))
        return 0
    sem_saida_no_timeout = not golden.get("saida_parcial_no_timeout")
    diffs = []
    for i, case in enumerate(golden["casos"]):
        now = run_case(cmd, case["entrada"], args.cwd, args.pasta_saida, golden.get("ignorar", []), args.timeout,
                       args.ensaio, i, plano)
        changed = comparar_caso(case, now, sem_saida_no_timeout)
        if changed:
            mostrar = {"codigo": "codigo", "stdout": "stdout", "stderr": "stderr", "efeitos": "efeitos",
                       "arquivos": "arquivos"}
            diffs.append({"entrada": case["entrada"], "campos_divergentes": changed,
                          "antes": {k: case.get(mostrar[k]) for k in changed},
                          "depois": {k: now.get(mostrar[k]) for k in changed}})
    saida = {"casos": len(golden["casos"]), "divergencias": diffs, "plano_sha256": sha_plano}
    avisos = []
    if golden.get("schema_version") != "fundacao.golden/2":
        avisos.append("golden do formato 1: compara só os trechos gravados (20.000/4.000 caracteres) e a foto da "
                      "pasta; grave de novo para comparar as saídas inteiras e os efeitos por caso")
    if sem_saida_no_timeout and any(c.get("codigo") == "timeout" for c in golden["casos"]):
        avisos.append("golden gravado quando o timeout descartava a saída parcial: nos casos com timeout, só o código "
                      "e os efeitos foram comparados; grave de novo")
    if avisos:
        saida["aviso"] = "; ".join(avisos)
    print(json.dumps(saida, ensure_ascii=False, indent=2))
    return 1 if diffs else 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
