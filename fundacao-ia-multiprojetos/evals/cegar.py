#!/usr/bin/env python3
"""Notas cegas do ensaio contrastivo: cegar | notas | revelar.

[Decisão; harness2, P4] Método adaptado de Harness² (arXiv:2610.14224, github.com/google-research/harness2,
commit 1cfe254, Apache-2.0); texto e código próprios. Quem dá a nota não sabe de qual braço (de qual texto da
skill) veio cada saída, e o mapa só é aberto depois que todas as notas estão gravadas no livro-caixa.

  cegar   --iteracao <bancada> --livro <pasta> --destino <pasta cega> [--semente <s>] [--so 10,13]
          copia as saídas de cada execução de todos os braços para <pasta cega>/<avaliação>-<letra>/saidas, com
          as letras embaralhadas por semente, e os fatos do verificador sem os caminhos da bancada e da área; o
          mapa letra -> (braço, execução) fica no livro, com o SHA-256 no livro.json; grava <pasta cega>/notas.json
          para preencher. A pasta cega é uma raiz separada, nova ou vazia, fora da bancada, do workspace e do pai
          dele, da área do executor, do livro e do repositório, nem ao lado dele (isolamento.conferir_vizinhanca):
          quem dá as notas recebe SÓ ela. Revisão de segurança da 1.7.7 (R177-VAL-07): as cópias ficavam em
          <bancada>/cego/, ao lado dos originais em eval-*/<braço>/run-*/outputs, e o SHA-256 recuperava o mapa.
          Só entra execução com partida concluída no livro que confira (livro_avaliacoes.situacao_da_execucao,
          R177-VAL-08): execução sem lastro (sem partida, rastro que não confere) recusa tudo; a não comparável
          (partida não concluída, outro modelo, cópia da skill mudada) fica fora, listada.
  notas   --iteracao <bancada> --livro <pasta>
          confere a folha notas.json da pasta cega (todos os ids; uma nota por asserção, na ordem do
          eval_metadata.json, com passed = true | false | "nao_medido") e grava o SHA-256 dela no livro.
  revelar --iteracao <bancada> --livro <pasta>
          só com a folha gravada e inalterada e o mapa conferido: grava o grading.json de cada execução na
          bancada (a nota por execução que o resumo_k.py lê) e revelado.json na pasta cega.
Códigos: 0 ok; 2 uso incorreto; 3 recusado (nada gravado).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
import secrets
import string
import sys
from pathlib import Path

EVALS = Path(__file__).resolve().parent


def _irmao(nome: str):
    spec = importlib.util.spec_from_file_location(f"_{nome}_do_cegar", EVALS / f"{nome}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


iso = _irmao("isolamento")
lv = _irmao("livro_avaliacoes")
Recusa = lv.Recusa


def _ler(caminho: Path):
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.is_file() else None


def _gravar(caminho: Path, dados) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _entrada(dados: dict, it: Path) -> dict | None:
    """A entrada desta bancada no livro, por qualquer nome dela (terceira passada da revisão, R177C-B-08)."""
    return next((e for chave, e in dados.get("cegos", {}).items() if iso.mesmo_lugar(chave, it)), None)


def _sem_caminhos(valor, caminhos: list[Path]):
    """Fatos sem os caminhos da área e da bancada (o grader não fica sabendo onde está a execução)."""
    texto = json.dumps(valor, ensure_ascii=False)
    formas = {(f, rotulo) for c, rotulo in caminhos for f in (str(c), c.as_posix(), json.dumps(str(c))[1:-1])}
    for forma, rotulo in sorted(formas, key=lambda x: len(x[0]), reverse=True):
        texto = texto.replace(forma, rotulo)
    return json.loads(texto)


def _pasta_cega(it: Path, livro: Path, dados: dict, destino: Path) -> Path:
    """A raiz separada do material cego: nova ou vazia, não ligação, longe da bancada, do livro e da área."""
    pasta = Path(destino)
    if iso.e_ligacao(pasta) or (pasta.exists() and (not pasta.is_dir() or any(pasta.iterdir()))):
        raise Recusa(f"a pasta cega tem de ser nova ou vazia (e não ligação): {pasta}")
    estado = _ler(it / "isolamento.json") or {}
    fontes = [*(b["pasta"] for b in dados["identidade"]["bracos"].values()),
              *(estado.get("bracos") or {}).values(), livro]
    problemas = iso.conferir_vizinhanca(pasta, it, fontes, papel="a pasta cega")
    if estado.get("area") and (iso.dentro(pasta, estado["area"]) or iso.dentro(estado["area"], pasta)):
        problemas.append(f"a pasta cega e a área do executor ({iso.resolvido(estado['area'])}) se sobrepõem")
    if problemas:
        raise Recusa("; ".join(problemas))
    return iso.resolvido(pasta)


def cegar(it: Path, livro: Path, semente: str, escolha: set[int] | None, destino: Path) -> dict:
    dados = lv.carregar(livro)
    if _entrada(dados, it):
        raise Recusa("esta bancada já foi cegada neste livro (um mapa só por bancada)")
    cega = _pasta_cega(it, livro, dados, destino)
    pedidos = _ler(it / "prompts.json") or {}
    estado = _ler(it / "isolamento.json") or {}
    if estado.get("livro") and not iso.mesmo_lugar(estado["livro"], livro):
        raise Recusa(f"a bancada foi preparada com outro livro ({estado['livro']})")
    area = estado.get("area")
    fatos = _ler(it / "_referencias" / "fatos.json") or {}
    mapa, folha, sem_lastro, fora, usadas = {}, {}, [], [], {}  # usadas: uma partida, uma execução
    for edir in sorted(it.glob("eval-*")):
        meta = _ler(edir / "eval_metadata.json") or {}
        eid = meta.get("eval_id")
        if eid is None or (escolha and eid not in escolha):
            continue
        execucoes = []
        for cfg, run in sorted((cfg.name, run.name) for cfg in edir.iterdir() if cfg.is_dir()
                               for run in cfg.glob("run-*") if (run / "outputs").is_dir()):
            chave = f"{eid}/{cfg}/{run}"
            situacao, motivo = lv.situacao_da_execucao(livro, dados, pedidos.get(chave),
                                                       edir / cfg / run / "trace.jsonl", chave, usadas)
            if situacao == "valida":
                execucoes.append((cfg, run))
            else:
                (sem_lastro if situacao == "sem_lastro" else fora).append(f"{chave}: {motivo}")
        if len(execucoes) > len(string.ascii_uppercase):
            raise ValueError(f"E{eid}: mais de 26 execuções para cegar")
        random.Random(f"{semente}|{eid}").shuffle(execucoes)
        for letra, (braco, run) in zip(string.ascii_uppercase, execucoes):
            mapa[f"{eid}-{letra}"] = {"avaliacao": eid, "pasta": f"{edir.name}/{braco}/{run}", "braco": braco,
                                      "execucao": run}
            folha[f"{eid}-{letra}"] = {"avaliacao": eid, "expectations": [
                {"text": a, "passed": None, "evidence": ""} for a in meta.get("assertions", [])]}
    if sem_lastro:
        raise Recusa("execuções sem lastro no livro (nada foi cegado): " + "; ".join(sem_lastro))
    if not mapa:
        raise Recusa("nenhuma execução com saídas e partida válida para cegar" + (f" (fora: {'; '.join(fora)})"
                                                                                 if fora else ""))
    for ident, alvo in mapa.items():  # só depois de montar o mapa inteiro: recusa acima não deixa cópia pela metade
        iso.copiar_arquivos(it / alvo["pasta"] / "outputs", cega / ident / "saidas")
        pedido = pedidos.get(f"{alvo['avaliacao']}/{alvo['braco']}/{alvo['execucao']}", {})
        caminhos = [(it, "<bancada>")] + ([(Path(pedido["ambiente"]).parent, "<execucao>")] if pedido else []) + (
            [(Path(area), "<area>")] if area else [])
        if fatos.get(alvo["pasta"]) is not None:
            _gravar(cega / ident / "fatos.json", _sem_caminhos(fatos[alvo["pasta"]], caminhos))
    arquivo_mapa = Path(livro) / f"cego-{hashlib.sha256(str(it).encode('utf-8')).hexdigest()[:8]}.json"
    _gravar(lv._comum(arquivo_mapa, "mapa cego"), {"bancada": str(it), "semente": semente, "ids": mapa})
    _gravar(cega / "notas.json", folha)
    dados.setdefault("cegos", {})[str(it)] = {
        "mapa": arquivo_mapa.name, "mapa_sha256": lv.sha256_arquivo(arquivo_mapa), "ids": sorted(mapa),
        "pasta_cega": str(cega), "cegado_em": lv.agora(), "notas_sha256": None, "notas_gravadas_em": None,
        "revelado_em": None}
    lv.salvar(livro, dados)
    return {"ok": True, "ids": sorted(mapa), "folha": str(cega / "notas.json"), "fora_do_cegamento": fora,
            "entregar": f"a quem dá as notas, só a pasta cega {cega} (nunca a bancada, a área nem o livro)"}


def _folha(it: Path, entrada: dict) -> Path:
    """notas.json da pasta cega desta bancada (livro de antes da R177-VAL-07: <bancada>/cego)."""
    return lv._comum(Path(entrada.get("pasta_cega") or it / "cego") / "notas.json", "folha de notas")


def _conferir_folha(it: Path, folha_arq: Path, ids: list[str]) -> dict:
    folha = _ler(folha_arq)
    if not isinstance(folha, dict) or sorted(folha) != sorted(ids):
        raise Recusa("a folha notas.json da pasta cega não tem exatamente os ids cegados")
    for ident in ids:
        eid = folha[ident].get("avaliacao")
        meta = next((_ler(e / "eval_metadata.json") for e in it.glob(f"eval-{eid}-*")), None) or {}
        itens = folha[ident].get("expectations")
        textos = [i.get("text") for i in itens] if isinstance(itens, list) and all(isinstance(i, dict) for i in itens) \
            else None
        if textos != meta.get("assertions"):
            raise Recusa(f"{ident}: as notas não seguem as asserções do eval_metadata.json (texto e ordem)")
        if any(not (i.get("passed") is True or i.get("passed") is False or i.get("passed") == "nao_medido")
               for i in itens):
            raise Recusa(f"{ident}: nota incompleta (passed = true, false ou \"nao_medido\" em todas as asserções)")
    return folha


def notas(it: Path, livro: Path) -> dict:
    dados = lv.carregar(livro)
    entrada = _entrada(dados, it)
    if not entrada:
        raise Recusa("bancada não cegada neste livro (rode `cegar`)")
    if entrada["revelado_em"]:
        raise Recusa("o mapa já foi revelado: as notas não mudam mais")
    folha_arq = _folha(it, entrada)
    _conferir_folha(it, folha_arq, entrada["ids"])
    entrada.update(notas_sha256=lv.sha256_arquivo(folha_arq), notas_gravadas_em=lv.agora())
    lv.salvar(livro, dados)
    return {"ok": True, "notas_sha256": entrada["notas_sha256"]}


def revelar(it: Path, livro: Path) -> dict:
    dados = lv.carregar(livro)
    entrada = _entrada(dados, it)
    if not entrada or not entrada.get("notas_sha256"):
        raise Recusa("revelar só depois de todas as notas gravadas com hash no livro (`notas`)")
    folha_arq = _folha(it, entrada)
    if not folha_arq.is_file() or lv.sha256_arquivo(folha_arq) != entrada["notas_sha256"]:
        raise Recusa("a folha de notas mudou depois de gravada no livro")
    arquivo_mapa = lv._comum(Path(livro) / entrada["mapa"], "mapa cego")
    if not arquivo_mapa.is_file() or lv.sha256_arquivo(arquivo_mapa) != entrada["mapa_sha256"]:
        raise Recusa("o mapa cego não confere com o hash gravado no livro")
    folha, mapa = _conferir_folha(it, folha_arq, entrada["ids"]), _ler(arquivo_mapa)["ids"]
    escritas = {}
    for ident, alvo in mapa.items():
        itens = folha[ident]["expectations"]
        aprovadas, reprovadas = sum(i["passed"] is True for i in itens), sum(i["passed"] is False for i in itens)
        nota = {"expectations": itens, "summary": {"passed": aprovadas, "failed": reprovadas, "total": len(itens),
                                                   "pass_rate": round(aprovadas / len(itens), 4) if itens else 0.0},
                "nota_cega": {"id": ident, "notas_sha256": entrada["notas_sha256"],
                              "livro": str(iso.resolvido(livro))}}  # o resumo_k confere as partidas nele
        destino = it / alvo["pasta"] / "grading.json"
        if destino.exists() and _ler(destino) != nota:
            raise Recusa(f"{alvo['pasta']} já tem outra nota (grading.json): nada foi sobrescrito")
        escritas[destino] = nota
    for destino, nota in escritas.items():
        _gravar(destino, nota)
    _gravar(folha_arq.parent / "revelado.json", mapa)
    entrada["revelado_em"] = entrada["revelado_em"] or lv.agora()
    lv.salvar(livro, dados)
    return {"ok": True, "revelado": mapa}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("acao", choices=["cegar", "notas", "revelar"])
    ap.add_argument("--iteracao", type=Path, required=True)
    ap.add_argument("--livro", type=Path, required=True)
    ap.add_argument("--semente", help="semente do embaralhamento (padrão: nova)")
    ap.add_argument("--so", help="ids, ex.: 10,13")
    ap.add_argument("--destino", type=Path, help="cegar: a pasta cega, raiz separada que vai SÓ para quem dá as notas")
    args = ap.parse_args()
    it = iso.resolvido(args.iteracao)
    try:
        if args.acao == "cegar":
            if args.destino is None:
                raise ValueError("informe --destino: a pasta cega, fora da bancada, da área e do livro")
            escolha = {int(x) for x in args.so.split(",")} if args.so else None
            saida = cegar(it, args.livro, args.semente or secrets.token_hex(8), escolha, args.destino)
        elif args.acao == "notas":
            saida = notas(it, args.livro)
        else:
            saida = revelar(it, args.livro)
    except Recusa as exc:
        print(json.dumps({"recusado": str(exc), "gravado": "nada"}, ensure_ascii=False), file=sys.stderr)
        return 3
    except ValueError as exc:
        print(json.dumps({"erro": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(saida, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
