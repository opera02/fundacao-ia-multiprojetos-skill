#!/usr/bin/env python3
"""Partidas do livro-caixa amarradas às execuções da bancada (apoio de livro_avaliacoes.py, cegar.py e resumo_k.py).

[Decisão; harness2, P1] Revisão de segurança da 1.7.7 (R177-VAL-08): a partida não guardava a execução que rodou
nem o rastro dela, e o `cegar` e o `resumo_k` contavam toda pasta `run-*`; com teto 1 e uma partida, três execuções
foram cegadas, reveladas e contadas como "passou". Aqui:
- `vinculo` (no `iniciar`): o pedido do prompts.json com o id neutro dado, do mesmo caso e braço, numa bancada
  preparada com a skill deste braço no livro, com a cópia da skill do executor e o ambiente como o preparo os
  deixou (a partida grava o id neutro; o `fechar` grava o SHA-256 do rastro e reconfere a cópia);
- `situacao_da_execucao` (no `cegar` e no `resumo_k`): "valida" só com partida concluída, dentro do teto, amarrada
  ao id neutro, com a transcrição guardada íntegra e igual ao `trace.jsonl` da bancada, o modelo esperado e a cópia
  da skill sem mudança; "sem_lastro" (sem partida, rastro que não confere, partida de outro caso, além do teto) e
  "nao_comparavel" (partida não concluída, outro modelo, cópia mudada) nunca contam como aprovada. Segunda passada
  da revisão: uma partida dá lastro a uma execução só (a da chave amarrada no `iniciar`, uma vez por passada); com
  o id e o rastro copiados para outra execução, a outra fica "sem partida".
- Terceira passada da revisão (R177C-B-06): o lastro ficava preso à chave e à ordem, e a cópia da bancada inteira
  (`iteration-1` como `iteration-2`) ou da pasta da avaliação ganhava o lastro da mesma partida. O `vinculo` exige
  que o `registro` do pedido seja a pasta da execução na bancada (`<bancada>/eval-<id>-<nome>/<braço>/run-<k>`, da
  chave dele, sem ligação), e `situacao_da_execucao` só dá lastro ao rastro dessa pasta.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

EVALS = Path(__file__).resolve().parent


def _irmao(nome: str):
    spec = importlib.util.spec_from_file_location(f"_{nome}_das_partidas", EVALS / f"{nome}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


iso = _irmao("isolamento")
rastro = _irmao("medidas_do_rastro")


class Recusa(Exception):
    """Pedido recusado: nada foi gravado (código 3)."""


def _sha256(caminho: Path) -> str:
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


def _ler_json(caminho: Path) -> dict:
    try:
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def copia_da_skill(caminho: str | None) -> str | None:
    """Hash da cópia da skill do executor (o de isolamento.hash_da_skill); None no braço sem skill."""
    if not caminho:
        return None
    try:
        return iso.hash_da_skill(iso.manifesto_da_skill(Path(caminho)))
    except (OSError, RuntimeError):
        return "ilegível"


def _pastas_da_execucao(registro: Path) -> tuple[Path, Path, Path]:
    """`run-<k>`, o braço e `eval-<id>-<nome>`: as pastas da execução na bancada, de baixo para cima."""
    return registro, registro.parent, registro.parent.parent


def _registro_na_bancada(it: Path, chave: str, avaliacao: int, braco: str, registro) -> None:
    """Recusa o `registro` do pedido que não é a pasta da execução na bancada: `<bancada>/eval-<avaliação>-<nome>/
    <braço>/run-<k>`, com o `run-<k>` da chave, pasta comum (nem ela nem as de cima, até a bancada, são ligação).
    É a pasta do rastro a que a partida dá lastro (terceira passada da revisão de segurança da 1.7.7, R177C-B-06)."""
    reg = Path(registro) if isinstance(registro, str) and registro else None
    if reg is None or not reg.is_dir() or any(iso.e_ligacao(p) for p in _pastas_da_execucao(reg)) \
            or not iso.mesmo_lugar(reg.parent.parent.parent, it) or reg.name != chave.rsplit("/", 1)[-1] \
            or reg.parent.name != braco or not reg.parent.parent.name.startswith(f"eval-{avaliacao}-"):
        raise Recusa(f"o registro da execução no prompts.json ({registro}) não é a pasta dela na bancada "
                     f"(<bancada>/eval-{avaliacao}-<nome>/{braco}/{chave.rsplit('/', 1)[-1]}, sem ligação)")


def vinculo(it: Path, execucao: str, avaliacao: int, braco: str, sha_do_braco: str) -> dict:
    """O que a partida grava da execução que vai rodar; recusa o que não confere com o preparo, inclusive o registro
    que não é a pasta da execução na bancada (R177C-B-06)."""
    it = iso.resolvido(it)
    chave, pedido = next(((c, p) for c, p in _ler_json(it / "prompts.json").items()
                          if isinstance(p, dict) and p.get("id") == execucao), (None, None))
    if pedido is None:
        raise Recusa(f"execução {execucao} sem pedido no prompts.json da bancada {it}")
    if (pedido.get("avaliacao"), pedido.get("braco")) != (avaliacao, braco):
        raise Recusa(f"a execução {execucao} é da E{pedido.get('avaliacao')}, braço {pedido.get('braco')}")
    _registro_na_bancada(it, chave, avaliacao, braco, pedido.get("registro"))
    estado = _ler_json(it / "isolamento.json")
    if (estado.get("skills") or {}).get(braco) != sha_do_braco:
        raise Recusa(f"a bancada foi preparada com outra skill no braço {braco} (não a deste livro)")
    copia = copia_da_skill(pedido.get("skill"))
    if copia != pedido.get("skill_sha256"):
        raise Recusa("a cópia da skill do executor não é a do preparo (mudou ou bancada antiga): prepare de novo")
    amb = Path(pedido.get("ambiente") or it / "(sem ambiente)")
    impressao = iso.impressao_do_ambiente(amb, amb.parent) if amb.is_dir() else {"(ambiente)": "ausente"}
    gravada = (((estado.get("ambientes") or {}).get(f"{avaliacao}/{chave.rsplit('/', 1)[-1]}") or {})
               .get("bracos") or {}).get(braco)
    if hashlib.sha256(json.dumps(sorted(impressao.items())).encode()).hexdigest() != gravada:
        raise Recusa("o ambiente da execução não é o do preparo (já rodou?): prepare de novo")
    return {"execucao": execucao, "chave": chave, "bancada": str(it), "registro": pedido.get("registro"),
            "skill_copia": pedido.get("skill"), "skill_copia_sha256": copia}


def _da_pasta(registro, pasta: Path) -> bool:
    """O rastro fica na pasta da execução gravada no `iniciar` (o `registro` da partida), e nenhuma das pastas da
    execução na bancada é ligação (terceira passada da revisão de segurança da 1.7.7, R177C-B-06)."""
    return isinstance(registro, str) and bool(registro) \
        and not any(iso.e_ligacao(p) for p in _pastas_da_execucao(pasta)) and iso.mesmo_lugar(registro, pasta)


def situacao_da_execucao(livro: Path, dados: dict, pedido: dict | None, trace: Path, chave: str | None = None,
                         usadas: dict | None = None) -> tuple[str, str]:
    """("valida" | "sem_lastro" | "nao_comparavel", motivo ou rótulo da partida) de uma execução da bancada.
    `chave`: a da execução no prompts.json (`<avaliação>/<braço>/run-<k>`); `usadas`: rótulo -> execução que já
    recebeu lastro nesta passada (o chamador guarda entre as execuções). Uma partida dá lastro a uma execução só:
    a amarrada a ela no `iniciar` e, numa passada, a primeira que a usa; outra com o mesmo id e o mesmo rastro
    (copiados) fica "sem partida" (segunda passada da revisão de segurança da 1.7.7, limite do R177-VAL-08). E só ao
    rastro da pasta gravada no `iniciar`: a cópia da bancada ou da pasta da avaliação fica "sem partida", qualquer que
    seja a ordem (terceira passada, R177C-B-06)."""
    if not pedido or not pedido.get("id"):
        return "sem_lastro", "execução sem id neutro no prompts.json (layout antigo)"
    ident = dados["identidade"]
    do_id = [(i, p) for i, p in enumerate(dados["partidas"]) if p.get("execucao") == pedido["id"]]
    da_chave = [(i, p) for i, p in do_id if chave is None or p.get("chave") == chave]
    if not da_chave:
        outras = "".join(f" (a partida {p['rotulo']} é da execução {p.get('chave')})" for _, p in do_id)
        return "sem_lastro", f"sem partida no livro{outras}"
    minhas = [(i, p) for i, p in da_chave if _da_pasta(p.get("registro"), Path(trace).parent)]
    if not minhas:
        gravadas = "; ".join(f"{p['rotulo']}: {'/'.join(Path(p.get('registro') or '?').parts[-4:])}"
                             for _, p in da_chave)
        return "sem_lastro", f"sem partida nesta pasta (a gravada no iniciar é outra: {gravadas})"
    if any((p["avaliacao"], p["braco"]) != (pedido.get("avaliacao"), pedido.get("braco")) for _, p in minhas):
        return "sem_lastro", "partida de outro caso ou braço amarrada a esta execução"
    concluidas = [(i, p) for i, p in minhas if p["estado"] == "concluida"]
    if not concluidas:
        return "nao_comparavel", f"partida não concluída ({', '.join(sorted({p['estado'] for _, p in minhas}))})"
    if iso.e_ligacao(trace) or not Path(trace).is_file():
        return "sem_lastro", "sem rastro (trace.jsonl) da execução na bancada"
    sha = _sha256(trace)
    i, p = next(((i, p) for i, p in concluidas if (p.get("transcricao") or {}).get("sha256") == sha), (None, None))
    if p is None:
        return "sem_lastro", "o rastro da execução não confere com a transcrição guardada no livro"
    if i >= ident["teto"]:
        return "sem_lastro", f"partida {p['rotulo']} além do teto de {ident['teto']}"
    guardada = Path(livro) / p["transcricao"]["arquivo"]
    if iso.e_ligacao(guardada) or not guardada.is_file() or _sha256(guardada) != sha:
        return "sem_lastro", f"transcrição guardada de {p['rotulo']} ausente ou alterada"
    problema = rastro.problema_de_modelo(p.get("medidas") or {}, ident["modelo_esperado"],
                                         ident.get("modelos_auxiliares") or [])
    if problema:
        return "nao_comparavel", f"{p['rotulo']}: {problema}"
    if p.get("skill_copia_sha256") and p.get("skill_copia_ao_fechar") != p["skill_copia_sha256"]:
        return "nao_comparavel", f"{p['rotulo']}: a cópia da skill do executor mudou durante a partida"
    if usadas is not None:
        execucao = Path(trace).parent.as_posix()
        if usadas.setdefault(p["rotulo"], execucao) != execucao:
            return "sem_lastro", (f"sem partida: {p['rotulo']} já dá lastro a "
                                  f"{'/'.join(Path(usadas[p['rotulo']]).parts[-3:])}")
    return "valida", p["rotulo"]
