#!/usr/bin/env python3
"""O item da folha de decisões do plano de execução do `caracterizar.py`, em linguagem simples.

Só lê o plano montado por `execucao_isolada.py` (e, para um aviso, onde fica a pasta pessoal); não executa nada. O
texto diz o que o código importado vê e grava — a cópia, as entradas (quantas e onde) e a pasta gravável — e avisa o
que fica fora da cópia e do projeto dela ou na pasta pessoal [revisão de segurança da 1.7.7, R177-FB-01]; diz o que
prende o código que o programa roda — o manifesto da cópia, menos o que ele não vê, ou, sem cópia, nada além do
programa [R177-FB-02] — e, com a cópia, avisa quando o código não fica preso, com os motivos, e mostra a pasta de
trabalho [segunda passada, R177B-B-02]; diz que a cópia é conferida antes e depois de cada caso e avisa da pasta
gravável que fica dentro dela [R177B-B-03]; e termina com o SHA-256 que o aceite prende.
"""

from __future__ import annotations

import os
from pathlib import Path

_MIB = 1024 * 1024
POUCOS = 5  # até quantos caminhos a folha cita pelo nome; acima disso, os primeiros e quantos faltam


def _casa() -> str:
    return os.path.realpath(os.path.expanduser("~"))


def _dentro(caminho: str, pasta: str) -> bool:
    return Path(caminho).is_relative_to(pasta)  # comparação do texto do caminho, como no lançador


def _lista(itens: list[str]) -> str:
    return ", ".join(itens[:POUCOS]) + (f" e mais {len(itens) - POUCOS}" if len(itens) > POUCOS else "")


def entradas(lista: list[str]) -> str:
    """Quantas entradas e onde: a pasta comum e os caminhos relativos a ela (os primeiros, se forem muitos)."""
    if not lista:
        return "nenhuma entrada"
    nome = "1 entrada" if len(lista) == 1 else f"{len(lista)} entradas"
    try:
        comum = os.path.commonpath(lista) if len(lista) > 1 else os.path.dirname(lista[0])
    except ValueError:  # discos diferentes, no Windows: não há pasta comum
        return f"{nome}: {_lista(lista)}"
    if comum in lista:  # todas iguais
        comum = os.path.dirname(comum)
    return f"{nome} em {comum} ({_lista([os.path.relpath(e, comum) for e in lista])})"


def gravavel(plano: dict) -> str:
    g = plano["gravavel"]
    if not g:
        return ("nenhuma pasta gravável (só o /tmp próprio)" if plano["isolamento"] == "bwrap"
                else "nenhuma pasta gravável indicada")
    if g["tipo"] == "ensaio":
        return f"a pasta gravável {g['caminho']} (uma subpasta nova e vazia por caso)"
    return f"a pasta gravável {g['caminho']} (inteira, com o que já houver nela)"


def codigo(plano: dict) -> str:
    """O que prende o código que o programa roda: o hash do plano prende só o programa (`comando[0]`), e o manifesto, a
    cópia; o código só está preso se o plano não lista motivo em contrário (`codigo_nao_preso`)."""
    man = plano["manifesto"]
    if not man:
        return (f"ATENÇÃO: só o programa {plano['programa']['caminho']} está preso pelo hash; o código que ele roda (o "
                "script e os módulos que ele importa) não está e pode ser trocado depois do aceite sem mudar o plano")
    motivos = plano.get("codigo_nao_preso") or []
    conferida = "conferida contra ele na montagem e antes e depois de cada caso (se mudar, a execução para)"
    if motivos:
        texto = (f"ATENÇÃO: o código que o programa roda NÃO está preso: {'; '.join(motivos)}; ele pode ser trocado "
                 f"depois do aceite sem mudar o plano. O manifesto {man['arquivo']} (SHA-256 {man['sha256']}) prende "
                 f"só a cópia, {conferida}")
    else:
        texto = (f"Código importado preso pelo manifesto {man['arquivo']} (SHA-256 {man['sha256']}): a cópia é "
                 f"{conferida}, inclusive os módulos que o programa importa dela")
    if man.get("fora_do_manifesto"):
        texto += (". ATENÇÃO: a cópia tem o que o manifesto não vê nem prende (ligação, nome de segredo, exclusão dele "
                  f"ou pasta que ele ignora): {_lista(man['fora_do_manifesto'])}")
    if man.get("pasta_gravavel_na_copia"):  # [R177B-B-03]
        texto += (f". ATENÇÃO: a pasta gravável fica dentro da cópia ({man['pasta_gravavel_na_copia']}/): o que for "
                  "gravado nela não é conferido nem fica preso")
    return texto


def avisos_de_local(plano: dict) -> list[str]:
    """A cópia fora de um projeto da fundação; entrada ou pasta gravável fora da cópia e do projeto dela; e o que fica
    na pasta pessoal sem estar no projeto (se a fundação mora na pasta pessoal, o projeto não é aviso)."""
    copia, projeto, casa = plano["copia"], plano.get("projeto_da_copia"), _casa()
    grav = [plano["gravavel"]["caminho"]] if plano["gravavel"] else []
    avisos = []
    if copia and not projeto:
        avisos.append("ATENÇÃO: a cópia não fica num projeto da fundação (<raiz>/projects/<projeto>/)")
    area = [p for p in (copia, projeto) if p]
    fora = [c for c in plano["entradas"] + grav if area and not any(_dentro(c, a) for a in area)]
    if fora:
        avisos.append(f"ATENÇÃO: fora da cópia e do projeto dela: {_lista(fora)}")
    pessoais = [c for c in ([copia] if copia else []) + plano["entradas"] + grav
                if _dentro(os.path.realpath(c), casa) and not (projeto and _dentro(c, projeto))]
    if pessoais:
        avisos.append(f"ATENÇÃO: na sua pasta pessoal: {_lista(pessoais)}")
    return avisos


def para_a_folha(plano: dict, sha: str) -> str:
    """O item da folha de decisões em linguagem simples, com o hash que o aceite prende."""
    lim, copia = plano["limites"], plano["copia"]
    if plano["isolamento"] == "bwrap":
        quem = (f"isolado pelo bubblewrap: sem rede; o programa vê só o sistema (só leitura), a cópia {copia} (só "
                f"leitura), {entradas(plano['entradas'])} (só leitura, uma por caso) e {gravavel(plano)}; nada da sua "
                "pasta pessoal, da raiz da fundação, de state/ ou de outros projetos além da cópia, das entradas e da "
                "pasta gravável que você indicou")
    else:
        quem = (f"SEM ISOLAMENTO (motivo: {plano['motivo_sem_isolamento']}): o programa roda com toda a autoridade da "
                f"sua conta — lê e grava o que você lê e grava, e usa a rede; cópia: {copia or 'nenhuma'}; "
                f"{entradas(plano['entradas'])}; {gravavel(plano)}")
    return " ".join([f"Executar o código importado ({plano['acao']}), {quem}.", f"{codigo(plano)}.",
                     *(f"{aviso}." for aviso in avisos_de_local(plano)),
                     f"Comando: {' '.join(plano['comando'])}, na pasta de trabalho {plano['cwd']}. Limites por caso: "
                     f"{lim['tempo_s']} s, saída até {lim['saida_bytes'] // _MIB} MiB por fluxo, memória "
                     f"{lim['memoria_bytes'] // _MIB} MiB, {lim['processos']} processos. Variáveis a mais: "
                     f"{', '.join(plano['variaveis_pedidas']) or 'nenhuma'}. Plano SHA-256 {sha}."])
