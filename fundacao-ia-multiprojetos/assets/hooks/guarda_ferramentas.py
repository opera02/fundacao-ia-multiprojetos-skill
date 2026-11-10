#!/usr/bin/env python3
"""Hook PreToolUse da sessão de projeto no Ubuntu: lista positiva de ferramentas (contratos do lote 2 da 1.7.10, §7).

Registro (pacote HOST, só no perfil WSL de projeto): matcher `.*`, comando `python3 -I -B` com o caminho absoluto
`<raiz>/.claude/hooks/guarda_ferramentas.py`. Decide pelo nome da ferramenta (`tool_name`), sem ler arquivo; a entrada
só é lida na ferramenta de subagentes:
- FUNDACAO_FERRAMENTAS: nomes exatos, separados por vírgula — a mesma lista do `--tools` do lançador. Ausente ou vazia:
  nega tudo (falha fechada). Sem curinga: `*` só casaria uma ferramenta chamada `*`.
- Subagentes (1.7.10.2): no Claude Code 2.1.302 a ferramenta se chama `Agent`; o `--tools` ainda aceita o nome antigo
  `Task`, e o evento chega como `Agent`. Os dois nomes valem pelo mesmo item da lista. A entrada passa por uma lista
  fechada de campos (CAMPOS_DO_AGENTE): `isolation` (`remote` leva o agente para a nuvem; `worktree` cria uma cópia
  git), `cwd` (outra pasta de trabalho), `name`, `team_name` e `mode` (agente com nome, equipe) e qualquer campo novo
  são negados; cada campo aceito tem o tipo conferido (texto ou booleano), sem depender da validação do binário. O
  `subagent_type`, quando vem, só com um dos nomes de TIPOS_DO_AGENTE, os dos tipos embutidos, ou um tipo de arquivo
  listado em FUNDACAO_AGENTES (1.7.11, lote A1; formato abaixo). O guarda confere o nome, não a origem da definição: no
  2.1.302, uma definição de outra fonte com o mesmo nome toma o lugar da embutida. Com o `--setting-sources local` do
  lançador, as de usuário e de projeto não carregam, e as de plugin levam o prefixo do plugin; o preparo recusa agentes
  nas managed settings (`/etc/claude-code/.claude/agents`). `SubagentHandback`, o canal do relatório do subagente para
  quem o chamou, vale com o mesmo item da lista. O agente local roda no mesmo
  processo; pelo esquema lido no binário 2.1.302 (03/11/2026), o evento de hook que vem de um subagente traz
  `agent_id` e `agent_type`, e as ferramentas dele passam por estes hooks, pelo perfil e pelo sandbox da sessão. No
  `web-fetch` embutido, isso não foi localizado: a prova 13 do checklist do projeto mede.
- FUNDACAO_AGENTES (1.7.11, lote A1; desenho de skills e agentes, §2.4): os agentes de arquivo que a ficha de aberturas
  abriu, `<plugin>:<agente>=Ferramenta|Ferramenta,<plugin>:<outro>=Ferramenta`. Ausente ou vazia, só os embutidos valem.
  Malformada (item sem `=`, nome sem uma `:`, ferramenta repetida, fora de uma lista curta de nomes, `Agent`, `Task`,
  `Skill`, `NotebookEdit`, `SubagentHandback` ou MCP, mais de 10 ferramentas ou 20 agentes): nenhum tipo de arquivo
  vale, e os embutidos seguem (falha fechada só no que é novo). O guarda não lê o arquivo do agente.
- Três travas valem para o evento que vem de um subagente (traz `agent_id` ou `agent_type`; na sessão principal não
  valem, porque um `cd` do Bash mudaria o `cwd` e travaria a sessão):
  1. `agent_type` tem de ser um tipo de TIPOS_DO_EVENTO (os embutidos) ou um agente de FUNDACAO_AGENTES; qualquer outro
     valor (vazio, que não é texto, ou ausente com `agent_id`) nega toda ferramenta: o subagente nasceu por um caminho
     que a ficha não abriu (hook de plugin, skill em fork, definição de outra fonte);
  2. o agente de arquivo só usa as ferramentas dele (o `SubagentHandback`, o relatório de volta, fica de fora da conta);
  3. o `cwd` do evento, só como texto (`posixpath.normpath`, sem ler o disco), tem de ficar em
     `FUNDACAO_RAIZ/projects/FUNDACAO_PROJECT` ou no temp do projeto (`TMPDIR`, que tem de ser uma pasta
     `fundacao-ia-<projeto>`). Sem a raiz ou o projeto no ambiente, ou sem `cwd` no evento, nega. Ligação simbólica não
     é seguida: é limite do guarda, que não abre arquivo.
- Skill (1.7.11, lote A1): com FUNDACAO_SKILLS no ambiente (`<plugin>:<skill>`, separadas por vírgula; o preparo grava as
  skills dos plugins da ficha; sem skill, `-`), a ferramenta Skill só passa com o nome exato de `skill` na lista; `-`,
  variável vazia (perfil anterior) ou malformada nega toda skill. Sem a variável, vale o comportamento de antes (a
  ferramenta Skill segue a lista do `--tools`). A forma da entrada da Skill no hook ({"skill": nome}) e o `agent_type`
  de cada caminho de subagente ainda dependem de medida no canário (M-S6 e M-A3 do desenho): a trava nega o que não
  reconhece.
- `mcp__<servidor>__<ferramenta>`: só com o servidor em FUNDACAO_MCP_PERMITIDAS, escrito como o nome do servidor ou
  como `mcp__<servidor>__*`. Padrões largos (`mcp__*`, `mcp__ccd_*`) não liberam nada aqui; nome com `__` ambíguo
  (mais de um separador, `___`) é negado. A lista é vazia sem a seção `mcp` da ficha.
- FUNDACAO_MCP_FERRAMENTAS (1.7.11, lote L2; desenho da jaula, §4.3): os nomes completos `mcp__<servidor>__<ferramenta>`
  que a ficha lista, separados por vírgula. PRESENTE (o perfil gerado a traz sempre, vazia sem a seção), só passa a
  ferramenta MCP cujo nome exato está nela: servidor liberado com ferramenta fora da lista, ferramenta nova ou renomeada,
  variável vazia ou malformada (item que não é `mcp__<servidor>__<ferramenta>` exato, repetido ou acima de 40) negam
  toda MCP. Gravação ou consulta valem igual: o que decide é estar listada na ficha assinada. Ausente: o comportamento da
  1.7.10 (servidor inteiro), que o preparo nunca gera e os invariantes do perfil recusam.
- Qualquer outro nome é negado, inclusive ferramenta nova de uma versão do Claude Code (mensagens entre sessões,
  agendamentos, Artifact): o `--tools` fecha as conhecidas e este hook as que aparecerem (CRITICA-DESENHO, "ferramentas
  internas do Claude Code"; REESCOPO, item 5).
Saída: a negação no formato do guarda_caminho.py, em JSON só com ASCII; liberado = sem saída (segue o fluxo normal de
permissões e os demais hooks). Evento ilegível, vazio, sem `tool_name` ou erro inesperado: nega.
Limite (honestidade, §0 dos contratos): guarda-corpo do processo do Claude Code, não barreira de SO. Um mod ou uma
aprovação que ignore hooks passa por cima, e com a raiz em /mnt/e o sandbox não confinou os comandos nas sondas de
31/10/2026: lá o isolamento entre projetos é lógico até o canário passar no ambiente real.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import sys

LIMITE_NOME = 120
SERVIDOR = re.compile(r"[A-Za-z0-9_.-]+\Z")
PADRAO_DO_SERVIDOR = re.compile(r"mcp__([A-Za-z0-9_.-]+)__\*\Z")
AGENTE = frozenset({"Agent", "Task"})  # o nome da 2.1.302 e o antigo, que o --tools ainda aceita
RELATORIO_DO_SUBAGENTE = "SubagentHandback"  # o relatório do subagente para quem o chamou (2.1.302)
# Os campos aceitos e o tipo de cada um (o esquema da 2.1.302: textos e o booleano do segundo plano).
CAMPOS_DO_AGENTE = {"description": str, "prompt": str, "subagent_type": str, "model": str, "effort": str,
                    "run_in_background": bool}
TIPOS_DO_AGENTE = frozenset({"general-purpose", "web-fetch", "Explore", "Plan"})  # embutidos; sem tipo: general-purpose
# Os `agent_type` que o evento de um subagente pode trazer sem a ficha. Começa pelos quatro embutidos; a medida M-A3 do
# desenho (canário) diz se o `fork` aparece e se entra aqui. Fora desta lista e de FUNDACAO_AGENTES, tudo é negado.
TIPOS_DO_EVENTO = frozenset({"general-purpose", "web-fetch", "Explore", "Plan"})
# Agentes de arquivo (FUNDACAO_AGENTES): `<plugin>:<agente>=Ferramenta|Ferramenta`, itens separados por vírgula.
NOME_DO_ITEM = r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}"
_FERRAMENTA = r"[A-Za-z][A-Za-z0-9]{0,39}"
AGENTE_DE_ARQUIVO = re.compile(rf"({NOME_DO_ITEM}:{NOME_DO_ITEM})=({_FERRAMENTA}(?:\|{_FERRAMENTA})*)\Z")
SKILL_DA_FICHA = re.compile(rf"{NOME_DO_ITEM}:{NOME_DO_ITEM}\Z")
SEM_SKILLS = "-"  # o valor do FUNDACAO_SKILLS sem skill (o preparo grava o mesmo; não vazio, F13 da revisão final)
# Nunca na lista de um agente de arquivo (o nome com `_`, como o MCP, nem casa com a forma acima).
FERRAMENTAS_FORA_DO_AGENTE = frozenset({"Agent", "Task", "Skill", "NotebookEdit", RELATORIO_DO_SUBAGENTE})
MAX_AGENTES, MAX_FERRAMENTAS_DO_AGENTE, MAX_VARIAVEL = 20, 10, 8192
PROJETO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
CHAVE_MCP_FERRAMENTAS = "FUNDACAO_MCP_FERRAMENTAS"
FERRAMENTA_MCP = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")  # a parte da ferramenta, como a ficha a escreve
MAX_FERRAMENTAS_MCP = 40
CAMPOS_NEGADOS_DO_AGENTE = {
    "isolation": "'remote' leva o agente para a nuvem e 'worktree' cria uma cópia git",
    "cwd": "o agente rodaria em outra pasta de trabalho",
    "name": "agente com nome é endereçado por mensagens entre agentes (equipes)",
    "team_name": "equipes de agentes ficam fora desta sessão",
    "mode": "o modo de permissão do agente é o da sessão",
}


def deny(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def _lista(texto: str | None) -> list[str]:
    return [item.strip() for item in (texto or "").split(",") if item.strip()]


def _mostravel(nome: str) -> str:
    """O nome para a mensagem: só caracteres imprimíveis, com teto (o nome vem do evento)."""
    limpo = "".join(c if c.isprintable() else "?" for c in nome)
    return limpo if len(limpo) <= LIMITE_NOME else limpo[:LIMITE_NOME] + "..."


def servidores_permitidos(texto: str | None) -> set[str]:
    """Servidores MCP liberados: o nome exato ou `mcp__<servidor>__*`; os demais padrões não liberam nada."""
    servidores = set()
    for item in _lista(texto):
        m = PADRAO_DO_SERVIDOR.fullmatch(item)
        nome = m.group(1) if m else item
        if SERVIDOR.fullmatch(nome) and "__" not in nome:
            servidores.add(nome)
    return servidores


def servidor_mcp(nome: str) -> str | None:
    """O servidor de `mcp__<servidor>__<ferramenta>`; None quando o nome é ambíguo ou malformado."""
    resto = nome[len("mcp__"):]
    if resto.count("__") != 1 or "___" in resto:
        return None
    servidor, ferramenta = resto.split("__")
    return servidor if servidor and ferramenta and SERVIDOR.fullmatch(servidor) else None


def ferramentas_mcp_da_ficha(texto) -> tuple[frozenset[str], bool]:
    """FUNDACAO_MCP_FERRAMENTAS (presente) -> (nomes exatos liberados, bem formada). Vazia: (vazio, True): nenhuma MCP.
    Qualquer item fora de `mcp__<servidor>__<ferramenta>` (um só `__` de cada lado do servidor, ferramenta em
    [a-z][a-z0-9_]*, sem `_` no fim nem `__`), repetido, ou mais de 40: (vazio, False)."""
    if not isinstance(texto, str) or len(texto) > MAX_VARIAVEL:
        return frozenset(), False
    itens = _lista(texto)
    if len(itens) > MAX_FERRAMENTAS_MCP or len(set(itens)) != len(itens):
        return frozenset(), False
    for item in itens:
        servidor = servidor_mcp(item) if item.startswith("mcp__") else None
        ferramenta = item[len("mcp__") + len(servidor) + 2:] if servidor else ""
        if not FERRAMENTA_MCP.fullmatch(ferramenta) or "__" in ferramenta or ferramenta.endswith("_"):
            return frozenset(), False
    return frozenset(itens), True


def agentes_de_arquivo(texto) -> tuple[dict[str, frozenset[str]], bool]:
    """FUNDACAO_AGENTES -> (`{tipo: ferramentas}`, bem formada). Ausente ou vazia: ({}, True). Qualquer defeito: ({}, False),
    isto é, nenhum tipo de arquivo vale (os embutidos não dependem desta variável)."""
    if texto is None:
        return {}, True
    if not isinstance(texto, str) or len(texto) > MAX_VARIAVEL:
        return {}, False
    agentes: dict[str, frozenset[str]] = {}
    for item in _lista(texto):
        m = AGENTE_DE_ARQUIVO.fullmatch(item)
        if not m or m.group(1) in agentes:
            return {}, False
        ferramentas = m.group(2).split("|")
        if (len(set(ferramentas)) != len(ferramentas) or len(ferramentas) > MAX_FERRAMENTAS_DO_AGENTE
                or set(ferramentas) & FERRAMENTAS_FORA_DO_AGENTE):
            return {}, False
        agentes[m.group(1)] = frozenset(ferramentas)
    if len(agentes) > MAX_AGENTES:
        return {}, False
    return agentes, True


def skills_da_ficha(texto) -> tuple[frozenset[str], bool]:
    """FUNDACAO_SKILLS (presente) -> (skills liberadas, bem formada). Item fora da forma `<plugin>:<skill>`, ou texto
    grande demais: (vazio, False). `-` (SEM_SKILLS, o que o preparo grava sem skill) e vazia: (vazio, True): nenhuma skill.
    A vazia vale por causa dos perfis anteriores ao F13, até o novo preparo; o `-` é o valor não vazio que o preparo grava
    hoje, para não depender do repasse de variável vazia ao hook (que ninguém mediu)."""
    if not isinstance(texto, str) or len(texto) > MAX_VARIAVEL:
        return frozenset(), False
    if texto == SEM_SKILLS:
        return frozenset(), True
    itens = _lista(texto)
    if not all(SKILL_DA_FICHA.fullmatch(i) for i in itens):
        return frozenset(), False
    return frozenset(itens), True


def _caminho_absoluto(texto) -> str | None:
    """O caminho só como texto (sem tocar o disco): absoluto, sem controle, normalizado; `//x` (raiz alternativa) não vale."""
    if not isinstance(texto, str) or not texto or len(texto) > 4096 or any(c < " " or c == "\x7f" for c in texto):
        return None
    if not texto.startswith("/"):
        return None
    norma = posixpath.normpath(texto)
    return None if norma.startswith("//") else norma


def pastas_do_projeto(env: dict) -> list[str]:
    """As pastas em que o `cwd` de um subagente pode ficar: `<raiz>/projects/<projeto>` e o temp do projeto (`TMPDIR`
    só se for uma pasta `fundacao-ia-<projeto>` com pai que não seja a raiz do disco). Sem raiz ou projeto: nenhuma."""
    projeto, raiz = env.get("FUNDACAO_PROJECT"), _caminho_absoluto(env.get("FUNDACAO_RAIZ"))
    if not isinstance(projeto, str) or not PROJETO.fullmatch(projeto) or raiz is None:
        return []
    pastas = [posixpath.join(raiz, "projects", projeto)]
    temp = _caminho_absoluto(env.get("TMPDIR"))
    if temp and posixpath.basename(temp) == "fundacao-ia-" + projeto and posixpath.dirname(temp) not in ("/", ""):
        pastas.append(temp)
    return pastas


def dentro_de(cwd: str, pastas: list[str]) -> bool:
    return any(cwd == p or cwd.startswith(p.rstrip("/") + "/") for p in pastas)


def conferir_subagente(event: dict, env: dict, agentes: dict[str, frozenset[str]], nome: str) -> dict | None:
    """As travas do evento que vem de um subagente (traz `agent_id` ou `agent_type`): o tipo, o `cwd` e, no agente de
    arquivo, a ferramenta. None = passou por elas (as demais regras do guarda seguem valendo)."""
    tipo = event.get("agent_type")
    if not isinstance(tipo, str) or not tipo or (tipo not in TIPOS_DO_EVENTO and tipo not in agentes):
        return deny(f"o subagente que chamou '{_mostravel(nome)}' tem tipo que a ficha de aberturas não abriu "
                    f"('{_mostravel(tipo) if isinstance(tipo, str) and tipo else 'sem tipo'}'): toda ferramenta dele está "
                    "negada por segurança. Ele nasceu por um caminho que esta sessão não liberou (agente de arquivo fora "
                    f"da ficha, hook ou skill de plugin). Os tipos liberados são {', '.join(sorted(TIPOS_DO_EVENTO))} e "
                    "os agentes da ficha; se precisar de outro, peça ao titular.")
    cwd = _caminho_absoluto(event.get("cwd"))
    pastas = pastas_do_projeto(env)
    if cwd is None or not pastas or not dentro_de(cwd, pastas):
        onde = "sem pasta de trabalho no evento" if cwd is None else f"em '{_mostravel(cwd)}'"
        return deny(f"o subagente '{_mostravel(tipo)}' está trabalhando {onde}, fora da pasta do projeto: toda "
                    "ferramenta dele está negada por segurança. Ele só pode ficar dentro de projects/<projeto> (ou no "
                    "temp do projeto). Se a pasta do projeto não está no ambiente (FUNDACAO_RAIZ, FUNDACAO_PROJECT), "
                    "abra a sessão pelo lançador do projeto.")
    limite = agentes.get(tipo)
    if limite is not None and nome not in limite and nome != RELATORIO_DO_SUBAGENTE:
        return deny(f"o agente '{_mostravel(tipo)}' só pode usar {', '.join(sorted(limite))} (a lista dele na ficha de "
                    f"aberturas): a ferramenta '{_mostravel(nome)}' está fora dela. Use uma dessas ou peça ao titular.")
    return None


def conferir_skill(entrada, texto) -> dict | None:
    """A ferramenta Skill com FUNDACAO_SKILLS presente: só o nome exato de `skill` que a ficha abriu."""
    liberadas, bem_formada = skills_da_ficha(texto)
    skill = entrada.get("skill") if isinstance(entrada, dict) else None
    if skill is None or not isinstance(skill, str):
        return deny("a ferramenta Skill veio sem o nome da skill (campo 'skill') em forma que o guarda reconheça: "
                    "negada por segurança.")
    if skill in liberadas:
        return None
    return deny(f"a skill '{_mostravel(skill)}' não está liberada neste projeto (FUNDACAO_SKILLS"
                f"{'' if bem_formada else ', malformada: nenhuma skill vale'}). Só abrem as skills dos plugins da "
                "ficha de aberturas assinada pelo titular, chamadas como <plugin>:<skill>; skill embutida ou de outro "
                "plugin fica fechada. Se ela for necessária, peça ao titular.")


def conferir_agente(entrada, agentes: dict[str, frozenset[str]] | None = None, bem_formada: bool = True) -> dict | None:
    """A entrada da ferramenta de subagentes: só os campos de CAMPOS_DO_AGENTE; o agente roda local, nesta pasta."""
    agentes = agentes or {}
    if not isinstance(entrada, dict):
        return deny("entrada da ferramenta Agent ilegível: negada por segurança")
    for campo in sorted(entrada, key=str):
        if campo in CAMPOS_DO_AGENTE:
            if not isinstance(entrada[campo], CAMPOS_DO_AGENTE[campo]):  # null também: o campo vem com o tipo dele
                return deny(f"o campo '{campo}' da ferramenta Agent veio fora do tipo esperado "
                            f"({CAMPOS_DO_AGENTE[campo].__name__}): negado por segurança; repita com o valor certo ou "
                            "sem o campo.")
            continue
        if campo in CAMPOS_NEGADOS_DO_AGENTE:
            return deny(f"a ferramenta Agent com o campo '{campo}' está negada nesta sessão "
                        f"({CAMPOS_NEGADOS_DO_AGENTE[campo]}): repita sem ele. O agente roda local, nesta pasta, com "
                        "os mesmos hooks, o mesmo perfil e o mesmo sandbox.")
        return deny(f"o campo '{_mostravel(str(campo))}' da ferramenta Agent está fora da lista fechada desta sessão "
                    f"({', '.join(sorted(CAMPOS_DO_AGENTE))}): repita sem ele; se ele for necessário, peça ao titular.")
    tipo = entrada.get("subagent_type")
    if tipo is not None and tipo not in TIPOS_DO_AGENTE and tipo not in agentes:
        aviso = ("" if bem_formada else " A lista de agentes da ficha (FUNDACAO_AGENTES) está malformada: nenhum agente "
                 "de arquivo vale.")
        return deny(f"o tipo de subagente '{_mostravel(str(tipo))}' está fora da lista desta sessão "
                    f"({', '.join(sorted(TIPOS_DO_AGENTE | set(agentes)))}): agente definido em arquivo (do projeto, de "
                    "pasta de dados ou de plugin) traz ferramentas, MCP e hooks próprios, que este guarda não confere, e "
                    "só abre se estiver na ficha de aberturas assinada pelo titular. Use um desses tipos (sem tipo, vale "
                    f"o general-purpose) ou peça ao titular.{aviso}")
    return None


def decide(event: dict, env: dict) -> dict | None:
    nome = event.get("tool_name")
    if not isinstance(nome, str) or not nome:
        return deny("evento sem nome de ferramenta: negado por segurança")
    ferramentas = set(_lista(env.get("FUNDACAO_FERRAMENTAS")))
    if not ferramentas:
        return deny("lista de ferramentas da sessão ausente (FUNDACAO_FERRAMENTAS): tudo negado. Abra a sessão pelo "
                    "lançador do projeto, que define a lista junto com o --tools.")
    agentes, bem_formada = agentes_de_arquivo(env.get("FUNDACAO_AGENTES"))
    if "agent_id" in event or "agent_type" in event:  # evento de subagente: as travas do tipo, do cwd e do agente
        negada = conferir_subagente(event, env, agentes, nome)
        if negada:
            return negada
    if nome.startswith("mcp__"):
        servidor = servidor_mcp(nome)
        if servidor is None:
            return deny(f"nome de ferramenta MCP ambíguo ou malformado ('{_mostravel(nome)}'): negado")
        if servidor not in servidores_permitidos(env.get("FUNDACAO_MCP_PERMITIDAS")):
            return deny(f"o servidor MCP '{_mostravel(servidor)}' não está liberado para este projeto "
                        "(FUNDACAO_MCP_PERMITIDAS). MCP de terceiro roda fora do sandbox: só abre com a ficha de "
                        "aberturas assinada pelo titular e a jaula (1.7.11).")
        if CHAVE_MCP_FERRAMENTAS in env:  # lote L2: só as ferramentas que a ficha lista, pelo nome exato
            liberadas, bem_formada = ferramentas_mcp_da_ficha(env[CHAVE_MCP_FERRAMENTAS])
            if nome not in liberadas:
                return deny(f"a ferramenta MCP '{_mostravel(nome)}' não está na lista da ficha de aberturas "
                            f"({CHAVE_MCP_FERRAMENTAS}{'' if bem_formada else ', malformada: nenhuma MCP vale'}): só "
                            "passam as ferramentas que a ficha assinada pelo titular lista pelo nome; ferramenta nova "
                            "ou renomeada do servidor fica negada até a ficha nova. Se ela for necessária, peça ao "
                            "titular.")
        return None
    if nome in AGENTE and ferramentas & AGENTE:
        return conferir_agente(event.get("tool_input"), agentes, bem_formada)
    if nome == RELATORIO_DO_SUBAGENTE and ferramentas & AGENTE:
        return None
    if nome == "Skill" and nome in ferramentas and "FUNDACAO_SKILLS" in env:
        return conferir_skill(event.get("tool_input"), env["FUNDACAO_SKILLS"])
    if nome in ferramentas:
        return None
    return deny(f"a ferramenta '{_mostravel(nome)}' está fora da lista fechada desta sessão (FUNDACAO_FERRAMENTAS, a "
                "mesma do --tools do lançador). Só a ficha de aberturas do projeto, assinada pelo titular, abre "
                "ferramenta nesta sessão (na 1.7.10: WebFetch e WebSearch); se ela for necessária, peça ao titular.")


def _recusar(*_):
    raise ValueError("entrada inválida")


def _objeto_sem_duplicatas(pares):
    objeto = {}
    for chave, valor in pares:
        if chave in objeto:
            _recusar()
        objeto[chave] = valor
    return objeto


def main() -> int:
    try:
        # Bytes em UTF-8: com -I o Python ignora PYTHONUTF8 e leria a entrada na página de código do Windows.
        event = json.loads(sys.stdin.buffer.read().decode("utf-8"), object_pairs_hook=_objeto_sem_duplicatas,
                           parse_constant=_recusar)
        if not isinstance(event, dict):
            raise ValueError("evento não é objeto")
        result = decide(event, dict(os.environ))
    except Exception:  # noqa: BLE001 — falha fechada: qualquer erro vira negativa
        result = deny("evento ilegível ou erro no hook: negado por segurança")
    if result:
        # JSON só com ASCII: a saída independe da página de código do console (cp1252 no Windows).
        sys.stdout.write(json.dumps(result, ensure_ascii=True) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
