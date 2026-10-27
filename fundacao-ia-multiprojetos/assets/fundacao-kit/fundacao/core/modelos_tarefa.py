"""Seleção declarada de modelo, sem classificador nem chamada a modelo para decidir.

O tipo vem do fluxo autorizado; texto de documento não define rota, modelo ou esforço.
IDs são configuração datada, nunca descobertos com chamada paga. Ausência de modelo
observado continua unknown, mesmo quando o modelo pedido é conhecido.
"""
import re
from dataclasses import replace

from .contracts import ValidationError

ID_MODELO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}\Z")
ESFORCOS = {"claude-cli": {"low", "medium", "high", "xhigh", "max"},
            "codex-cli": {"low", "medium", "high", "xhigh", "max", "ultra"},
            "local": set(), "simulado": set()}
CAMPOS = {"route", "provider_id", "model", "effort"}
ROTAS = {"claude-cli": {"cli_assinatura"}, "codex-cli": {"cli_assinatura"},
         "local": {"local"}, "simulado": {"simulado"}}


def validar_modelos(policy) -> list[str]:
    modelos = policy.get("task_models", {})
    if not isinstance(modelos, dict):
        return ["task_models deve ser objeto"]
    erros = []
    if modelos and policy.get("schema_version") != "fundacao.route/2":
        erros.append("task_models exige fundacao.route/2")
    for tipo, alvos in modelos.items():
        ordem = policy.get("task_routes", {}).get(tipo, [])
        if (not isinstance(alvos, list) or not alvos or not isinstance(ordem, list) or not ordem
                or not all(isinstance(r, str) for r in ordem)):
            erros.append(f"task_models.{tipo}: lista não vazia e task_routes correspondente obrigatórios")
            continue
        vistos, posicao = set(), -1
        for alvo in alvos:
            if not isinstance(alvo, dict) or set(alvo) != CAMPOS:
                erros.append(f"task_models.{tipo}: campos exatos {sorted(CAMPOS)}")
                continue
            rota, provedor, modelo, esforco = (alvo[k] for k in ("route", "provider_id", "model", "effort"))
            if not isinstance(rota, str) or rota not in ordem:
                erros.append(f"task_models.{tipo}: rota fora de task_routes")
            else:
                indice = ordem.index(rota)
                if indice < posicao:
                    erros.append(f"task_models.{tipo}: ordem de fallback difere de task_routes")
                posicao = indice
            if not isinstance(provedor, str) or provedor not in ESFORCOS:
                erros.append(f"task_models.{tipo}: provedor desconhecido")
            elif rota not in ROTAS[provedor]:
                erros.append(f"task_models.{tipo}: provedor incompatível com a rota")
            elif esforco is not None and (not isinstance(esforco, str) or esforco not in ESFORCOS[provedor]):
                erros.append(f"task_models.{tipo}: esforço não suportado pelo provedor")
            if not isinstance(modelo, str) or not ID_MODELO.fullmatch(modelo):
                erros.append(f"task_models.{tipo}: ID de modelo inválido")
            identidade = tuple(str(alvo[k]) for k in sorted(CAMPOS))
            if identidade in vistos:
                erros.append(f"task_models.{tipo}: alvo repetido")
            vistos.add(identidade)
    return erros


def alvos_da_tarefa(policy, task_kind, adapters, request):
    erros = validar_modelos(policy)
    if erros:
        raise ValidationError("política de modelos inválida: " + "; ".join(erros))
    alvos = policy.get("task_models", {}).get(task_kind)
    if alvos is None:
        return [(r, adapters.get(r), request) for r in policy["task_routes"].get(task_kind, [])]
    resultado = []
    for alvo in alvos:
        adapter = adapters.get((alvo["route"], alvo["provider_id"]))
        if adapter is not None and (getattr(adapter, "provider_id", None) != alvo["provider_id"]
                                    or getattr(adapter, "route", None) != alvo["route"]):
            raise ValidationError("adaptador não corresponde ao provedor e rota declarados")
        resultado.append((alvo["route"], adapter, replace(request, model=alvo["model"], effort=alvo["effort"])))
    return resultado


def flags_do_modelo(provedor, request, extras):
    if request is None or not getattr(request, "model", None):
        return []
    modelo, esforco = request.model, request.effort
    rota = "cli_assinatura"
    p = {"schema_version": "fundacao.route/2", "task_routes": {"x": [rota]}, "task_models": {"x": [
        {"route": rota, "provider_id": provedor, "model": modelo, "effort": esforco}]}}
    erros = validar_modelos(p)
    if erros or any(a in ("--model", "-m", "--effort", "--config", "-c") or
                    a.startswith(("--model=", "--effort=", "--config=", "model_reasoning_effort=", "-m", "-c")) for a in extras):
        raise ValidationError("modelo/esforço inválido ou sobrescrito por extra_args")
    flags = ["--model", modelo]
    if esforco:
        flags += ["--effort", esforco] if provedor == "claude-cli" else ["-c", f"model_reasoning_effort='{esforco}'"]
    return flags


def texto_do_saldo(valor):
    from decimal import Decimal, ROUND_DOWN
    from .usage import custo_decimal
    saldo = (valor.copy_abs() if isinstance(valor, Decimal) and valor.is_finite() and valor >= 0
             else custo_decimal(valor))
    if saldo is None:
        raise ValidationError("saldo de custo inválido")
    saldo = saldo.quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
    return f"{saldo:.2f}" if saldo == saldo.quantize(Decimal("0.01")) else f"{saldo:.6f}"
