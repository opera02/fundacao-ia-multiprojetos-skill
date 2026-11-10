"""Seções `navegador` e `outras_llm` da ficha de aberturas (1.7.11; DESENHO-JAULA §6 e §7.2; DECISAO-010 itens 3 e 4).

Navegador: perfil novo e só do projeto (o copiado do Windows fica fechado), domínios com as regras da rede, logins em nome
exato e modos fixos. Outras LLM: exatamente o Codex pela conta do ChatGPT do titular, com a conferência do plano (R55)
de até 90 dias. Saiu de `aberturas_regras.py` (teto de linhas do kit); o `aberturas_regras` o chama em `validar`,
`itens` e `descrever`, passando a si mesmo como `R`. Só biblioteca padrão e nenhum outro módulo do kit.
"""

from __future__ import annotations

import re
from datetime import date

TETO_LOGINS, TETO_CHAMADAS_DIA, VALIDADE_R55_DIAS = 20, 100, 90
# Navegador (jaula; perfil novo do projeto, DECISAO-010 item 3) e outras LLM (só o Codex pela conta do ChatGPT).
MODOS_NAVEGADOR = ("sessao", "login", "captcha")
CAMPOS_NAVEGADOR = ("dominios", "logins", "modos")
PROVEDORES_LLM, AUTENTICACOES_LLM, MODOS_LLM = ("openai-codex",), ("conta_chatgpt",), ("exec", "titular")
CAMPOS_LLM = ("provedor", "autenticacao", "modos", "conteudo_de_terceiros", "teto_chamadas_dia", "r55")
CAMPOS_R55 = ("plano", "treinamento_desligado", "conferido_em")
DATA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
PLANO = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._+-]{0,31}")


def _data(valor) -> date | None:
    try:
        return date.fromisoformat(valor) if isinstance(valor, str) and DATA.fullmatch(valor) else None
    except ValueError:
        return None


def _navegador(R, ficha: dict, erro, avisos: list) -> None:
    bloco = ficha.get("navegador")
    if R._vazio(bloco):
        return
    if not isinstance(bloco, dict):
        erro("navegador", 'use {"dominios": [...], "logins": [...], "modos": [...]}')
        return
    for chave in sorted(set(bloco) - set(CAMPOS_NAVEGADOR), key=str):
        erro(f"navegador.{R._chave(chave)}", "campo fora do esquema (additionalProperties: false): o perfil do navegador é "
             "sempre novo e só do projeto; perfil copiado do Windows fica fechado")
    if all(R._vazio(bloco.get(c)) for c in CAMPOS_NAVEGADOR):
        return
    dominios = bloco.get("dominios", [])
    validos: list[str] = []
    if not isinstance(dominios, list) or not 1 <= len(dominios) <= R.TETO_DOMINIOS:
        erro("navegador.dominios", f"lista de 1 a {R.TETO_DOMINIOS} domínios")
    else:
        for i, d in enumerate(dominios):
            motivo = R.problema_do_dominio(d) or ("domínio repetido" if d in validos else None)
            if motivo:
                erro(f"navegador.dominios[{i}]", motivo, valor=R.mostrar(d))
            else:
                validos.append(d)
                avisos += [{"campo": f"navegador.dominios[{i}]", "dominio": d, "motivo": a} for a in R.avisos_do_dominio(d)]
        if validos:
            avisos.append({"campo": "navegador.dominios", "dominio": None,
                           "motivo": "o navegador alcança estes sites; os comandos da sessão não"})
    logins = bloco.get("logins", [])
    if not isinstance(logins, list) or len(logins) > TETO_LOGINS:
        erro("navegador.logins", f"lista de até {TETO_LOGINS} nomes exatos de domínio")
    else:
        for i, d in enumerate(logins):
            motivo = ("login só em nome exato, sem curinga" if isinstance(d, str) and d.startswith("*.") else
                      R.problema_do_dominio(d) or ("login fora de navegador.dominios" if d not in validos else None)
                      or ("login repetido" if d in logins[:i] else None))
            if motivo:
                erro(f"navegador.logins[{i}]", motivo, valor=R.mostrar(d))
    modos = bloco.get("modos", [])
    if not isinstance(modos, list) or not 1 <= len(modos) <= len(MODOS_NAVEGADOR):
        erro("navegador.modos", "lista de 1 a 3 modos: " + ", ".join(MODOS_NAVEGADOR))
    else:
        for i, m in enumerate(modos):
            if m not in MODOS_NAVEGADOR or m in modos[:i]:
                erro(f"navegador.modos[{i}]", "modo desconhecido ou repetido (sessao, login, captcha)", valor=R.mostrar(m))


def _outras_llm(R, ficha: dict, hoje: date | None, erro, avisos: list) -> None:
    if "outras_llm" not in ficha or R._vazio(ficha["outras_llm"]):
        return
    lista = ficha["outras_llm"]
    if not isinstance(lista, list) or len(lista) != 1:
        erro("outras_llm", "exatamente 1 item (o Codex)")
        return
    item, campo = lista[0], "outras_llm[0]"
    if not isinstance(item, dict):
        erro(campo, "o item é um objeto com " + ", ".join(CAMPOS_LLM))
        return
    for chave in sorted(set(item) - set(CAMPOS_LLM), key=str):
        erro(f"{campo}.{R._chave(chave)}", "campo fora do esquema (additionalProperties: false); os domínios do "
                                          "provedor são fixos em código")
    for chave in CAMPOS_LLM:
        if chave not in item:
            erro(f"{campo}.{chave}", "campo obrigatório ausente")
    if "provedor" in item and item["provedor"] not in PROVEDORES_LLM:
        erro(campo + ".provedor", "só o Codex (openai-codex)", valor=R.mostrar(item["provedor"]))
    if "autenticacao" in item and item["autenticacao"] not in AUTENTICACOES_LLM:
        erro(campo + ".autenticacao", "só a conta do ChatGPT do titular (conta_chatgpt): decisão do titular de "
                                      "08/11/2026", valor=R.mostrar(item["autenticacao"]))
    modos = item.get("modos")
    if "modos" in item and (not isinstance(modos, list) or not 1 <= len(modos) <= len(MODOS_LLM)
                            or any(m not in MODOS_LLM or m in modos[:i] for i, m in enumerate(modos))):
        erro(campo + ".modos", "lista de 1 a 2 modos, sem repetir: " + ", ".join(MODOS_LLM))
    if "conteudo_de_terceiros" in item and not isinstance(item["conteudo_de_terceiros"], bool):
        erro(campo + ".conteudo_de_terceiros", "verdadeiro ou falso (se o conteúdo de clientes pode ir à OpenAI)")
    teto = item.get("teto_chamadas_dia")
    if "teto_chamadas_dia" in item and (isinstance(teto, bool) or not isinstance(teto, int)
                                        or not 1 <= teto <= TETO_CHAMADAS_DIA):
        erro(campo + ".teto_chamadas_dia", f"inteiro de 1 a {TETO_CHAMADAS_DIA}", valor=R.mostrar(teto))
    if "r55" in item:
        _r55(R, item["r55"], campo + ".r55", hoje, erro)
    avisos.append({"campo": "outras_llm", "dominio": None,
                   "motivo": "o conteúdo enviado ao Codex vai à OpenAI (EUA), fora desta máquina"})


def _r55(R, r55, campo: str, hoje: date | None, erro) -> None:
    if not isinstance(r55, dict) or set(r55) != set(CAMPOS_R55):
        erro(campo, "objeto com " + ", ".join(CAMPOS_R55) + ", sem outros campos")
        return
    if not isinstance(r55["plano"], str) or not PLANO.fullmatch(r55["plano"]):
        erro(campo + ".plano", "plano conferido: texto curto (letras, números, espaço, ponto, hífen), até 32",
             valor=R.mostrar(r55["plano"]))
    if r55["treinamento_desligado"] is not True:
        erro(campo + ".treinamento_desligado", "tem de ser true: sem o treinamento desligado no plano, o Codex não abre "
                                               "(R55)")
    data = _data(r55["conferido_em"])
    if data is None:
        erro(campo + ".conferido_em", "data no formato AAAA-MM-DD", valor=R.mostrar(r55["conferido_em"]))
    elif hoje is not None and data > hoje:
        erro(campo + ".conferido_em", f"data no futuro (hoje é {hoje.isoformat()})", valor=R.mostrar(r55["conferido_em"]))
    elif hoje is not None and (hoje - data).days > VALIDADE_R55_DIAS:
        erro(campo + ".conferido_em", f"conferência com mais de {VALIDADE_R55_DIAS} dias: confira o plano de novo e "
                                      "assine uma versão nova (R55)", vencida=True, valor=R.mostrar(r55["conferido_em"]))


def validar(R, ficha: dict, hoje, erro, avisos: list) -> None:
    _navegador(R, ficha, erro, avisos)
    _outras_llm(R, ficha, hoje, erro, avisos)


def _textos(valor) -> list[str]:
    return [v for v in valor if isinstance(v, str)] if isinstance(valor, list) else []


def _bloco(ficha, secao, tipo):
    valor = ficha.get(secao) if isinstance(ficha, dict) else None
    return valor if isinstance(valor, tipo) else tipo()


def itens(ficha) -> list[tuple[str, str]]:
    nav = _bloco(ficha, "navegador", dict)
    pares = [("navegador", d) for d in _textos(nav.get("dominios"))]
    pares += [("navegador-login", d) for d in _textos(nav.get("logins"))]
    pares += [("navegador-modo", m) for m in _textos(nav.get("modos"))]
    for c in (c for c in _bloco(ficha, "outras_llm", list) if isinstance(c, dict)):
        pares += [("outras_llm", f"{c.get('provedor')}:{m}") for m in _textos(c.get("modos"))]
    return pares


def descrever(R, ficha) -> list[dict]:
    saida = []
    nav = _bloco(ficha, "navegador", dict)
    if any(nav.get(c) for c in CAMPOS_NAVEGADOR):
        modos = ", ".join(R.mostrar(m) for m in _textos(nav.get("modos"))) or "nenhum"
        saida.append({"secao": "navegador", "item": "", "texto": (
            "Um navegador isolado, com perfil novo só deste projeto (nenhum perfil do Windows é copiado), poderá abrir os "
            f"sites abaixo nos modos {modos}: os comandos da sessão não alcançam esses sites; os logins que você fizer "
            "na janela do navegador ficam nesse perfil, ao alcance da sessão dentro da jaula.")})
        saida += [{"secao": "navegador", "item": d, "texto": f"O navegador poderá abrir {R.alvo(d)}."}
                  for d in _textos(nav.get("dominios"))]
        saida += [{"secao": "navegador-login", "item": d, "texto": f"Você poderá entrar (login) em {d} pela janela do "
                   "navegador; a senha e a sessão ficam no perfil novo do projeto."} for d in _textos(nav.get("logins"))]
    for c in (c for c in _bloco(ficha, "outras_llm", list) if isinstance(c, dict)):
        r55 = c.get("r55") if isinstance(c.get("r55"), dict) else {}
        saida.append({"secao": "outras_llm", "item": R.mostrar(c.get("provedor")), "texto": (
            f"O Codex ({R.mostrar(c.get('provedor'))}) poderá ser aberto pela sua conta do ChatGPT nos modos "
            f"{', '.join(R.mostrar(m) for m in _textos(c.get('modos')))}, com até {R.mostrar(c.get('teto_chamadas_dia'))} "
            "chamadas por dia: ele poderá receber conteúdo de clientes deste projeto, que vai à OpenAI (EUA); você "
            f"declarou em {R.mostrar(r55.get('conferido_em'))} que o treinamento com os seus dados está desligado no "
            f"plano {R.mostrar(r55.get('plano'))}.")})
    return saida
