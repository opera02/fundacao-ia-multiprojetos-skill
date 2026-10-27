"""Validação da política de rotas (registry/route_policy.json) ao carregar — análise do vibe-coding-toolkit,
21/10/2026, proposta 4. Tipo errado nunca vale como outro valor: `"enabled": "false"` em texto, teto em texto,
booleano, negativo ou NaN, rota citada que não existe e chave desconhecida são problemas, e a política com
problema não vale de jeito nenhum (falha fechada, em `routing.load_policy`).

Na raiz implantada, `registry/` é configuração local, e a rota `sigiloso` pode se afastar da distribuída por decisão
do titular (proposta 5): o desvio só vale com o SHA-256 da política em registry/configuracao-decidida.json, ligado a
um ACEITE ASSINADO do módulo de decisões sobre uma cópia exata da política (`desvio_sem_decisao`). Desde a 1.7.4
(avaliação E11, F-05: antes bastava existir um arquivo qualquer dentro da raiz, e a conferência só rodava na suíte),
desvio sem esse aceite fica sem efeito ao carregar a política (`routing.load_policy`: vale a rota distribuída) e o
`checar` da atualização avisa."""

from __future__ import annotations

import json
import math
import sqlite3
import subprocess
from pathlib import Path

from .contracts import ValidationError

CHAVES_DA_POLITICA = {"schema_version", "titular", "observacao", "routes", "task_routes", "task_models"}
CHAVES_DA_ROTA = {"enabled", "only_titular", "max_calls", "max_usd", "observacao"}
CONFIGURACAO_DECIDIDA = "configuracao-decidida.json"  # em registry/: arquivo de configuração -> hash e decisão
SCHEMA_DECIDIDA = "fundacao.configuracao_decidida/1"


def _booleano(valor) -> bool:
    return isinstance(valor, bool)


def _inteiro_nao_negativo(valor) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool) and valor >= 0


def _numero_nao_negativo(valor) -> bool:
    return (isinstance(valor, (int, float)) and not isinstance(valor, bool) and math.isfinite(valor)
            and valor >= 0)


def validar_politica(policy) -> list[str]:
    """Problemas da política de rotas; lista vazia = válida. Só aceita o tipo certo: texto "false",
    teto em texto, booleano no lugar de número, rota inexistente ou chave desconhecida são problemas."""
    if not isinstance(policy, dict):
        return ["a política não é um objeto JSON"]
    problemas = []
    if policy.get("schema_version") not in ("fundacao.route/1", "fundacao.route/2"):
        problemas.append("schema_version desconhecido (esperado fundacao.route/1 ou /2)")
    problemas += [f"chave desconhecida na política: {c}" for c in sorted(set(policy) - CHAVES_DA_POLITICA)]
    titular = policy.get("titular")
    if titular is not None and not (isinstance(titular, str) and titular.strip()):
        problemas.append("titular deve ser texto (a identidade do assinante) ou null")
    if not isinstance(policy.get("observacao", ""), str):
        problemas.append("observacao deve ser texto")
    rotas = policy.get("routes")
    if not isinstance(rotas, dict) or not rotas:
        problemas.append("routes deve ser um objeto com ao menos uma rota")
        rotas = {}
    for nome, cfg in rotas.items():
        if not isinstance(cfg, dict):
            problemas.append(f"rota {nome}: deve ser um objeto")
            continue
        problemas += [f"rota {nome}: chave desconhecida {c}" for c in sorted(set(cfg) - CHAVES_DA_ROTA)]
        for chave in ("enabled", "only_titular"):
            if not _booleano(cfg.get(chave)):
                problemas.append(f"rota {nome}: {chave} deve ser true ou false, sem aspas")
        if cfg.get("max_calls") is not None and not _inteiro_nao_negativo(cfg["max_calls"]):
            problemas.append(f"rota {nome}: max_calls deve ser inteiro maior ou igual a zero, ou null")
        if cfg.get("max_usd") is not None and not _numero_nao_negativo(cfg["max_usd"]):
            problemas.append(f"rota {nome}: max_usd deve ser número maior ou igual a zero, ou null")
        if not isinstance(cfg.get("observacao", ""), str):
            problemas.append(f"rota {nome}: observacao deve ser texto")
    ordens = policy.get("task_routes")
    if not isinstance(ordens, dict) or not ordens:
        problemas.append("task_routes deve ser um objeto com ao menos um tipo de tarefa")
        ordens = {}
    for tipo, ordem in ordens.items():
        if not isinstance(ordem, list) or not ordem or not all(isinstance(r, str) for r in ordem):
            problemas.append(f"task_routes.{tipo}: deve ser uma lista não vazia de nomes de rota")
            continue
        if len(set(ordem)) != len(ordem):
            problemas.append(f"task_routes.{tipo}: rota repetida")
        problemas += [f"task_routes.{tipo}: a rota {r} não existe em routes" for r in ordem if r not in rotas]
    if isinstance(policy.get("task_routes"), dict):
        from .modelos_tarefa import validar_modelos
        problemas += validar_modelos(policy)
    return problemas


def _vigente_na_trilha(raiz: Path, projeto: str, task_id: str) -> str | None:
    """SHA-256 da decisão vigente da tarefa na trilha de eventos da raiz, lida só para leitura; None se não houver."""
    from . import decisoes
    from .db import conectar_somente_leitura
    banco = raiz / "state" / "state.sqlite"
    if not banco.is_file():
        return None
    con = conectar_somente_leitura(banco)
    try:
        trilha = decisoes.registros_na_trilha(con, projeto, task_id)
    finally:
        con.close()
    return trilha[-1].get("sha256_decisao") if trilha else None


def hashes_decididos(raiz, arquivo: str) -> set[str]:
    """SHA-256 que um aceite do titular aprova para `arquivo` (relativo à raiz), pelos itens de
    registry/configuracao-decidida.json. O item cita uma decisão do módulo de decisões
    (`projects/<projeto>/decisoes/<id>.json`): ela precisa ser um aceite VÁLIDO — assinatura conferida contra a âncora
    desta máquina; sem âncora (laboratório), como mandar a política de decisões da raiz —, cuja entrega tem exatamente
    o SHA-256 do item, e a decisão VIGENTE da sua tarefa na trilha de eventos: registrada e não superada (a rejeição ou
    a correção registrada depois a revoga; revisão de segurança da 1.7.4, E11R-01 e E11R-02). Registro ilegível, item
    fora do formato, decisão inválida ou banco ilegível não aprovam nada (falha fechada)."""
    from . import decisoes  # tardio: o módulo de decisões é grande e só pesa quando há desvio
    raiz = Path(raiz).resolve()
    try:
        dados = json.loads((raiz / "registry" / CONFIGURACAO_DECIDIDA).read_text(encoding="utf-8"))
        ancora, politica = decisoes.resolver_ancora(), decisoes.carregar_politica(raiz)
    except (OSError, ValueError, ValidationError):
        return set()
    if not isinstance(dados, dict) or dados.get("schema_version") != SCHEMA_DECIDIDA:
        return set()
    aprovados = set()
    for item in dados.get("itens") if isinstance(dados.get("itens"), list) else ():
        if not isinstance(item, dict) or item.get("arquivo") != arquivo or not isinstance(item.get("sha256"), str):
            continue
        try:
            projeto, decisao = decisoes.pasta_da_decisao(raiz, raiz / str(item.get("decisao") or ""))
            r = decisoes.verificar_decisao(decisao, decisao.parent.parent, ancora, politica)
            if not (r.get("valida") and r.get("tipo") == "aceite"
                    and r["entrega"]["sha256"].lower() == item["sha256"].lower()):
                continue
            if _vigente_na_trilha(raiz, projeto, r["task_id"]) == r["sha256_decisao"]:
                aprovados.add(item["sha256"].lower())
        except (OSError, ValidationError, sqlite3.Error, subprocess.SubprocessError):
            continue
    return aprovados


def desvio_sem_decisao(raiz, politica: dict | None = None, sha256: str | None = None) -> str | None:
    """Problema, se a rota `sigiloso` se afasta da distribuída sem um aceite vigente que aprove o SHA-256 exato da
    política; senão None. `politica` e `sha256` vêm de UMA leitura dos bytes (`routing.ler_politica`): conferir um
    conteúdo e aplicar outro deixaria passar o desvio numa troca do arquivo entre duas leituras (E11R-03)."""
    from .routing import DEFAULT_POLICY, ler_politica  # tardio: routing importa este módulo

    if politica is None:
        politica, sha256 = ler_politica(raiz)
    if politica["task_routes"].get("sigiloso") == DEFAULT_POLICY["task_routes"]["sigiloso"]:
        return None
    if sha256 and sha256 in hashes_decididos(raiz, "registry/route_policy.json"):
        return None
    return ("a rota sigilosa da política local (registry/route_policy.json) difere da distribuída e o SHA-256 dela não "
            "está ligado a uma decisão registrada e vigente do titular (aceite assinado sobre uma cópia exata da "
            "política, citado em registry/" + CONFIGURACAO_DECIDIDA + "): o desvio fica sem efeito e vale a rota "
            "distribuída; assine e registre o aceite (capacidade 03 da skill) ou volte à política distribuída")
