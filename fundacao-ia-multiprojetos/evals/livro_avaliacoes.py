#!/usr/bin/env python3
"""Livro-caixa das rodadas reais de avaliação: abrir | iniciar | fechar | conferir | validade.

[Decisão; harness2, P1] Método adaptado de Harness² (arXiv:2610.14224, github.com/google-research/harness2,
commit 1cfe254, Apache-2.0); texto e código próprios. Cada partida de `claude -p` (ou de subagente) entra no
livro na hora, inclusive a interrompida: o teto autorizado conta partidas, não execuções avaliadas. O modelo vem
do rastro, nunca da memória de quem anota.

  abrir     --livro <pasta> --autorizacao "<palavras do titular>" --data <iso> --teto <n>
            --modelo-esperado <id> --braco <nome>=<pasta da skill> ... [--modelo-auxiliar <id> ...] [--versao-cli <v>]
            grava livro.json com a identidade do experimento: SHA-256 da skill de cada braço (sem evals/, texto
            canônico, por scripts/manifesto.py; braço sem skill: `--braco without_skill=`), do preparo da rodada
            (`_identidade_do_preparo`, com as fixtures inteiras; ligação nelas recusa), teto, modelo esperado,
            auxiliares aceitos só no `result` (o modelo pequeno do host, se houver) e autorização literal. Livro com
            outra identidade na pasta: recusa.
  iniciar   --livro <pasta> --rotulo E10-r1 --avaliacao 10 --braco <nome> [--iteracao <bancada> --execucao <id>]
            recusa (nada gravado) com o teto atingido — a partida interrompida conta —, rótulo repetido ou skill
            do braço ou preparo diferentes dos do `abrir`. Com a execução (o id neutro do prompts.json), amarra a
            partida a ela e recusa pedido de outro caso ou braço, registro que não é a pasta da execução na bancada
            (só o rastro dela tem lastro: R177C-B-06), bancada preparada com outra skill, cópia da skill do executor
            ou ambiente diferentes dos do preparo.
  fechar    --livro <pasta> --rotulo E10-r1 --estado concluida|interrompida|falhou [--transcricao <arquivo>]
            lê do rastro (stream-json) o modelo, os modelos que responderam, o custo informado pelo cliente
            (estimativa dele, não fatura), turnos, duração e consumo, com a regra do kit (ausente = "unknown", nunca
            0; medidas_do_rastro.py), e guarda a transcrição no livro, com hash (o SHA-256 do rastro; sem
            --transcricao, a da execução amarrada, `<registro>/trace.jsonl`). Reconfere a cópia da skill do executor.
  conferir  --livro <pasta>: iniciadas <= teto; rótulos únicos; toda partida com desfecho; modelo esperado no
            `init` e nas respostas (no `result`, ele e os auxiliares); transcrições guardadas íntegras; cópia da
            skill sem mudança. A saída traz o SHA-256 do livro (cite-o no AVALIACOES.md).
  validade  --livro <pasta> --skill <árvore> [--braco <nome>]: cada resultado "vale para o texto atual" ou é
            "resultado de outro texto", com os arquivos que diferem.
Revisão de segurança da 1.7.7 (R177-VAL-08): só o `iniciar` contava, a partida não guardava a execução e o modelo
vinha só do `init`; com teto 1 e uma partida, três execuções foram cegadas e contadas. `situacao_da_execucao` diz
ao `cegar.py` e ao `resumo_k.py` se uma execução tem partida concluída que confira.
Códigos: 0 ok; 1 conferir/validade acharam problema; 2 uso incorreto; 3 recusado (nada gravado).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

EVALS = Path(__file__).resolve().parent
SKILL = EVALS.parent
LIVRO = "livro.json"
FORMATO = "fundacao.livro-avaliacoes/1"
ESTADOS_FINAIS = ("concluida", "interrompida", "falhou")
ROTULO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
NOME_DE_BRACO = re.compile(r"[a-z][a-z0-9_]{0,31}")
UNKNOWN = "unknown"


def _irmao(nome: str, caminho: Path | None = None):
    """Módulo vizinho em evals/ (evals/ não é pacote) ou um script desta skill."""
    spec = importlib.util.spec_from_file_location(f"_{nome}_do_livro", caminho or EVALS / f"{nome}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


iso = _irmao("isolamento")
rastro = _irmao("medidas_do_rastro")
partidas_da_bancada = _irmao("partidas_da_bancada")
manifesto = _irmao("manifesto", SKILL / "scripts" / "manifesto.py")
Recusa = partidas_da_bancada.Recusa  # pedido recusado: nada foi gravado (código 3)
situacao_da_execucao = partidas_da_bancada.situacao_da_execucao


def agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_arquivo(caminho: Path) -> str:
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


def _comum(caminho: Path, papel: str) -> Path:
    """Arquivo que o livro lê ou grava: comum, nunca ligação (não segue caminho para fora)."""
    if iso.e_ligacao(caminho) or (caminho.exists() and not caminho.is_file()):
        raise Recusa(f"{papel} não é um arquivo comum (ligação ou pasta): {caminho}")
    return caminho


def carregar(livro: Path) -> dict:
    pasta = Path(livro)
    if iso.e_ligacao(pasta):
        raise Recusa(f"a pasta do livro é uma ligação: {pasta}")
    arq = _comum(pasta / LIVRO, LIVRO)
    if not arq.is_file():
        raise Recusa(f"livro inexistente: {arq} (use `abrir`)")
    dados = json.loads(arq.read_text(encoding="utf-8"))
    if not isinstance(dados, dict) or dados.get("formato") != FORMATO:
        raise Recusa(f"{arq} não é um livro de avaliações ({FORMATO})")
    return dados


def salvar(livro: Path, dados: dict) -> None:
    """Gravação atômica: arquivo temporário na mesma pasta e troca."""
    pasta = Path(livro)
    pasta.mkdir(parents=True, exist_ok=True)
    arq = _comum(pasta / LIVRO, LIVRO)
    tmp = pasta / f".{LIVRO}.tmp"
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, arq)


def identidade_das_fixtures() -> dict[str, str]:
    """Cada pasta e cada arquivo de evals/fixtures/, este pelo conteúdo (texto canônico de scripts/manifesto.py):
    é o que o preparo copia para os ambientes (isolamento.copiar_fixture). Entra tudo, inclusive as pastas que o
    manifesto ignora (`.venv`, `venv`, `node_modules`, `__pycache__`...) e o arquivo com nome de segredo (a `.env`
    fictícia do legado traz o valor que o verificador procura na E2 e na E3, R177B-A-03; no livro fica só o hash).
    Ligação recusa: a cópia levaria o outro lado (terceira passada da revisão de segurança da 1.7.7, R177C-B-07: o
    que o manifesto ignorava e o outro lado de uma junção entravam no ambiente sem mudar a identidade)."""
    fixtures = EVALS / "fixtures"
    if iso.e_ligacao(fixtures):
        raise Recusa("evals/fixtures é uma ligação: o preparo copiaria o outro lado")
    identidade = {}
    for caminho, ligacao in iso.percorrer(fixtures):
        rel = f"evals/fixtures/{caminho.relative_to(fixtures).as_posix()}"
        if ligacao:
            raise Recusa(f"ligação nas fixtures ({rel}): o preparo copiaria o outro lado; use arquivos comuns")
        try:
            if caminho.is_dir():
                identidade[f"{rel}/"] = "pasta"
            elif caminho.is_file():
                identidade[rel] = manifesto.file_hash(caminho, True)
            else:
                raise Recusa(f"nas fixtures, algo que não é pasta nem arquivo comum: {rel}")
        except OSError as exc:
            raise Recusa(f"fixture ilegível ({rel}): {type(exc).__name__}") from exc
    return identidade


def _identidade_do_preparo() -> dict[str, str]:
    """SHA-256 do que prepara, mede, cega e resume a rodada: cada arquivo de evals/ (scripts, evals.json, fixtures,
    cenarios/run_cenarios.py), cada script de scripts/ (manifesto.py, instalar_kit.py, retomada.py...) e o kit que
    monta os ambientes (um hash da árvore), com o texto canônico de scripts/manifesto.py; arquivo com nome de
    segredo entra só pelo nome, sem leitura. Na 1.7.7 eram só o evals.json e quatro scripts (R177-VAL-08).
    As fixtures de evals/ são fictícias e versionadas, e o preparo as copia para os ambientes: entram inteiras,
    pelo conteúdo, por `identidade_das_fixtures` (R177B-A-03 e R177C-B-07). O valor da `.env` não é impresso."""
    def arvore(pasta: Path) -> dict[str, str]:
        dados = manifesto.build(pasta, manifesto.politica_padrao(canonical=True))
        return {**{f["path"]: f["sha256"] for f in dados["arquivos"]},
                **{e["path"]: "excluído sem leitura" for e in dados["excluidos"]}}
    identidade = {f"evals/{rel}": h for rel, h in arvore(EVALS).items() if not rel.startswith("fixtures/")}
    identidade |= identidade_das_fixtures()
    identidade |= {f"scripts/{p.name}": manifesto.file_hash(p, True) for p in sorted((SKILL / "scripts").glob("*.py"))}
    kit = sorted(arvore(SKILL / "assets" / "fundacao-kit").items())
    identidade["assets/fundacao-kit/"] = hashlib.sha256(json.dumps(kit).encode("utf-8")).hexdigest()
    return identidade


def conferir_preparo(identidade: dict) -> None:
    """Recusa se o preparo da rodada mudou desde o `abrir` (diz o que mudou)."""
    atual, gravado = _identidade_do_preparo(), identidade["scripts"]
    if atual != gravado:
        dif = sorted(k for k in atual.keys() | gravado.keys() if atual.get(k) != gravado.get(k))
        raise Recusa(f"o preparo da rodada mudou desde o abrir ({', '.join(dif[:8])}): abra outro livro")


def _skill(pasta: str | None) -> tuple[dict, str]:
    """(manifesto, hash) da skill de um braço; braço sem skill = ({}, "sem_skill")."""
    if not pasta:
        return {}, "sem_skill"
    try:
        manifesto = iso.manifesto_da_skill(Path(pasta))
    except (OSError, RuntimeError) as exc:
        raise Recusa(f"skill do braço ilegível em {pasta}: {exc}") from exc
    return manifesto, iso.hash_da_skill(manifesto)


def bracos(dados: dict) -> dict[str, Path | None]:
    return {nome: (Path(b["pasta"]) if b["pasta"] else None) for nome, b in dados["identidade"]["bracos"].items()}


def teto_restante(dados: dict) -> int:
    return dados["identidade"]["teto"] - len(dados["partidas"])


def abrir(livro: Path, autorizacao: str, data: str, teto: int, modelo: str, bracos_arg: list[str],
          versao_cli: str | None = None, auxiliares: list[str] | None = None) -> dict:
    if teto < 1 or not bracos_arg or not autorizacao.strip():
        raise ValueError("informe a autorização literal, um teto >= 1 e ao menos um --braco")
    datetime.fromisoformat(data)  # data ISO 8601 (ValueError = uso incorreto)
    bracos_id, manifestos = {}, {}
    for item in bracos_arg:
        nome, sep, pasta = item.partition("=")
        if not sep or not NOME_DE_BRACO.fullmatch(nome) or nome in bracos_id:
            raise ValueError(f"--braco inválido ou repetido: {item!r} (use nome=<pasta>; sem skill: nome=)")
        pasta = None if pasta.strip() in ("", "-") else str(iso.resolvido(pasta))
        manifestos[nome], hash_skill = _skill(pasta)
        bracos_id[nome] = {"pasta": pasta, "sha256": hash_skill}
    identidade = {"autorizacao": autorizacao, "data": data, "teto": teto, "modelo_esperado": modelo,
                  "modelos_auxiliares": sorted(set(auxiliares or [])), "versao_cli": versao_cli or "nao_medida",
                  "bracos": bracos_id, "scripts": _identidade_do_preparo()}
    pasta = Path(livro)
    if (pasta / LIVRO).exists():
        if carregar(pasta)["identidade"] != identidade:
            raise Recusa("esta pasta já tem o livro de outro experimento (autorização, teto, modelo, skills ou "
                         "scripts diferentes): abra outro livro em outra pasta")
        return {"ok": True, "situacao": "livro já aberto com esta identidade", "livro": str(pasta / LIVRO)}
    pasta.mkdir(parents=True, exist_ok=True)
    for nome, manifesto in manifestos.items():
        if manifesto:
            _comum(pasta / f"skill-{nome}.json", "manifesto do braço").write_text(
                json.dumps(manifesto, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
                newline="\n")
    salvar(pasta, {"formato": FORMATO, "aberto_em": agora(), "identidade": identidade, "partidas": []})
    return {"ok": True, "situacao": "livro aberto", "livro": str(pasta / LIVRO), "teto": teto,
            "bracos": {n: b["sha256"] for n, b in bracos_id.items()}}


def iniciar(livro: Path, rotulo: str, avaliacao: int, braco: str, iteracao: Path | None = None,
            execucao: str | None = None) -> dict:
    if not ROTULO.fullmatch(rotulo):
        raise ValueError(f"rótulo inválido: {rotulo!r} (letras, dígitos, '.', '_' e '-'; até 64)")
    if (iteracao is None) != (execucao is None):
        raise ValueError("--iteracao e --execucao vão juntos (a bancada e o id neutro da execução)")
    dados = carregar(livro)
    ident = dados["identidade"]
    if braco not in ident["bracos"]:
        raise Recusa(f"braço desconhecido neste livro: {braco}")
    if any(p["rotulo"] == rotulo for p in dados["partidas"]):
        raise Recusa(f"rótulo repetido: {rotulo} (uma etapa sobrescreveria a outra)")
    if len(dados["partidas"]) >= ident["teto"]:
        raise Recusa(f"teto atingido: {len(dados['partidas'])} partida(s) iniciada(s), contando as interrompidas, "
                     f"para um teto de {ident['teto']}; outra partida pede nova autorização")
    conferir_preparo(ident)
    if _skill(ident["bracos"][braco]["pasta"])[1] != ident["bracos"][braco]["sha256"]:
        raise Recusa(f"a skill do braço {braco} mudou desde o abrir: abra outro livro")
    vinculo = partidas_da_bancada.vinculo(iteracao, execucao, avaliacao, braco, ident["bracos"][braco]["sha256"]) \
        if execucao else {}
    dados["partidas"].append({"rotulo": rotulo, "avaliacao": avaliacao, "braco": braco, **vinculo,
                              "iniciada_em": agora(), "estado": "iniciada"})
    salvar(livro, dados)
    return {"ok": True, "rotulo": rotulo, "restam": teto_restante(dados), "execucao": execucao or "não amarrada"}


def fechar(livro: Path, rotulo: str, estado: str, transcricao: Path | None) -> dict:
    if estado not in ESTADOS_FINAIS:
        raise ValueError(f"estado inválido: {estado} (use {', '.join(ESTADOS_FINAIS)})")
    dados = carregar(livro)
    partida = next((p for p in dados["partidas"] if p["rotulo"] == rotulo), None)
    if partida is None:
        raise Recusa(f"rótulo sem partida iniciada: {rotulo}")
    if partida["estado"] != "iniciada":
        raise Recusa(f"a partida {rotulo} já foi fechada ({partida['estado']})")
    if transcricao is None and partida.get("registro") and (Path(partida["registro"]) / "trace.jsonl").is_file():
        transcricao = Path(partida["registro"]) / "trace.jsonl"  # o rastro da execução amarrada
    destino = None
    if transcricao is not None:
        _comum(Path(transcricao), "transcrição")
        if not Path(transcricao).is_file():
            raise Recusa(f"transcrição inexistente: {transcricao}")
        destino = _comum(Path(livro) / "transcricoes" / f"{rotulo}.jsonl", "cópia da transcrição")
        if destino.exists():
            raise Recusa(f"já existe uma transcrição guardada para {rotulo}")
    partida["medidas"] = rastro.medidas_do_rastro(Path(transcricao) if transcricao else None, rotulo, estado)
    if destino is not None:
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(transcricao, destino)
        partida["transcricao"] = {"arquivo": destino.relative_to(Path(livro)).as_posix(),
                                  "sha256": sha256_arquivo(destino)}  # o SHA-256 do rastro (R177-VAL-08)
    if partida.get("skill_copia"):  # a cópia da skill do executor é conferida de novo antes de fechar
        partida["skill_copia_ao_fechar"] = partidas_da_bancada.copia_da_skill(partida["skill_copia"])
    partida.update(estado=estado, fechada_em=agora())
    salvar(livro, dados)
    return {"ok": True, "rotulo": rotulo, "estado": estado, "medidas": partida["medidas"]}


def conferir(livro: Path) -> tuple[dict, list[str]]:
    dados = carregar(livro)
    ident, partidas = dados["identidade"], dados["partidas"]
    esperado = ident["modelo_esperado"]
    problemas = []
    if len(partidas) > ident["teto"]:
        problemas.append(f"{len(partidas)} partidas iniciadas para um teto de {ident['teto']}")
    rotulos = Counter(p["rotulo"] for p in partidas)
    problemas += [f"rótulo repetido: {r}" for r, n in sorted(rotulos.items()) if n > 1]
    for p in partidas:
        rot = p["rotulo"]
        if p["estado"] == "iniciada":
            problemas.append(f"{rot}: aberta, não medida (partida sem desfecho registrado)")
            continue
        transc = p.get("transcricao")
        if transc:
            arq = Path(livro) / transc["arquivo"]
            if iso.e_ligacao(arq) or not arq.is_file() or sha256_arquivo(arq) != transc["sha256"]:
                problemas.append(f"{rot}: transcrição guardada ausente ou alterada")
            problema = rastro.problema_de_modelo(p.get("medidas", {}), esperado, ident.get("modelos_auxiliares", []),
                                                 exige_resposta=p["estado"] == "concluida")
            if problema:
                problemas.append(f"{rot}: {problema}")
        elif p["estado"] == "concluida":
            problemas.append(f"{rot}: concluída sem transcrição — resultado sem lastro")
        if p.get("skill_copia_sha256") and p.get("skill_copia_ao_fechar") != p["skill_copia_sha256"]:
            problemas.append(f"{rot}: a cópia da skill do executor mudou durante a partida (resultado de outro texto)")
    relatorio = {"livro_sha256": sha256_arquivo(Path(livro) / LIVRO), "teto": ident["teto"],
                 "iniciadas": len(partidas), "por_estado": dict(Counter(p["estado"] for p in partidas)),
                 "partidas": [{"rotulo": p["rotulo"], "avaliacao": p["avaliacao"], "braco": p["braco"],
                               "execucao": p.get("execucao", "não amarrada"), "estado": p["estado"],
                               "modelo": p.get("medidas", {}).get("modelo", UNKNOWN)} for p in partidas],
                 "problemas": problemas}
    return relatorio, problemas


def validade(livro: Path, skill: Path, braco: str | None = None) -> tuple[dict, bool]:
    dados = carregar(livro)
    atual = iso.manifesto_da_skill(Path(skill))
    resultados, de_outro_texto = [], False
    for nome, b in dados["identidade"]["bracos"].items():
        if (braco and nome != braco) or not b["pasta"]:
            continue
        gravado = json.loads(_comum(Path(livro) / f"skill-{nome}.json", "manifesto do braço").read_text(
            encoding="utf-8"))
        if iso.hash_da_skill(gravado) != b["sha256"]:
            raise Recusa(f"o manifesto gravado do braço {nome} não confere com o livro")
        dif = {"alterados": sorted(k for k in gravado.keys() & atual.keys() if gravado[k] != atual[k]),
               "ausentes": sorted(gravado.keys() - atual.keys()), "novos": sorted(atual.keys() - gravado.keys())}
        vale = not any(dif.values())
        for p in dados["partidas"]:
            if p["braco"] == nome and p["estado"] == "concluida":
                linha = {"rotulo": p["rotulo"], "braco": nome,
                         "situacao": "vale para o texto atual" if vale else "resultado de outro texto"}
                resultados.append(linha if vale else {**linha, "arquivos_que_diferem": dif})
                de_outro_texto = de_outro_texto or not vale
    return {"skill": str(Path(skill).resolve()), "resultados": resultados}, de_outro_texto


OBRIGATORIA = {"required": True}
OPCOES = {  # subcomando -> opções além de --livro
    "abrir": {"--autorizacao": OBRIGATORIA, "--data": OBRIGATORIA, "--teto": {"type": int, "required": True},
              "--modelo-esperado": OBRIGATORIA, "--versao-cli": {},
              "--braco": {"action": "append", "default": [], "metavar": "NOME=PASTA"},
              "--modelo-auxiliar": {"action": "append", "default": [], "metavar": "ID"}},
    "iniciar": {"--rotulo": OBRIGATORIA, "--avaliacao": {"type": int, "required": True}, "--braco": OBRIGATORIA,
                "--iteracao": {"type": Path}, "--execucao": {"metavar": "ID_NEUTRO"}},
    "fechar": {"--rotulo": OBRIGATORIA, "--estado": {"required": True, "choices": ESTADOS_FINAIS},
               "--transcricao": {"type": Path}},
    "conferir": {},
    "validade": {"--skill": {"type": Path, "required": True}, "--braco": {}},
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nome, opcoes in OPCOES.items():
        comando = sub.add_parser(nome)
        comando.add_argument("--livro", type=Path, required=True)
        for opcao, extras in opcoes.items():
            comando.add_argument(opcao, **extras)
    args = ap.parse_args()
    try:
        codigo = 0
        if args.cmd == "abrir":
            saida = abrir(args.livro, args.autorizacao, args.data, args.teto, args.modelo_esperado, args.braco,
                          args.versao_cli, args.modelo_auxiliar)
        elif args.cmd == "iniciar":
            saida = iniciar(args.livro, args.rotulo, args.avaliacao, args.braco, args.iteracao, args.execucao)
        elif args.cmd == "fechar":
            saida = fechar(args.livro, args.rotulo, args.estado, args.transcricao)
        elif args.cmd == "conferir":
            saida, problemas = conferir(args.livro)
            codigo = 1 if problemas else 0
        else:
            saida, outro = validade(args.livro, args.skill, args.braco)
            codigo = 1 if outro else 0
    except Recusa as exc:
        print(json.dumps({"recusado": str(exc), "gravado": "nada"}, ensure_ascii=False), file=sys.stderr)
        return 3
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"erro": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(saida, ensure_ascii=False, indent=2))
    return codigo


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
