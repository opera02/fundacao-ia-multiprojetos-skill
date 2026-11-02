#!/usr/bin/env python3
"""Hook PreToolUse de leitura: Read, Grep e Glob fora de outro projeto e de state/ (contratos do lote 2 da 1.7.10, §7).

Registro (HOST, perfis WSL e Windows): matcher `Read|Grep|Glob` (grupo separado do de `mcp__.*`), `python3 -I -B`
(Windows: `python -I -B`), `<raiz>/.claude/hooks/guarda_leitura.py`. Nega, sem ler arquivo: `<raiz>/projects/<x>/` com
x diferente de FUNDACAO_PROJECT (sem caixa; sem projeto válido, qualquer x: falha fechada), `<raiz>/state/` e, com
FUNDACAO_SEM_DADOS=1 (Windows), `<raiz>/projects/*/data/`, inclusive a do próprio projeto. Read: o `file_path`; Glob:
a pasta (`path` ou a atual) com o `pattern`; Grep: a pasta com cada pedaço do `glob` como o Claude Code o passa ao
ripgrep (por espaço e, fora de `{...}`, por vírgula; só `!`, ou nada, vale como tudo) e com o filtro inteiro.
Relativo parte do `cwd` do evento; `~`, `..`, chaves, ligação (caminho real), unidade (`E:\\`, `\\\\?\\E:\\`) e
`/mnt/e` traduzidos; sem caixa, sem ponto ou espaço no fim, sem `:fluxo`; nome curto 8.3 em `/mnt/<l>` fora do
Windows (o DrvFs o resolve, o caminho real não) casa qualquer nome. Padrão que POSSA casar caminho proibido é negado
(`projects/*/`, `**` da raiz ou de `projects/`, padrão sem pasta, que desce: E9 da coorte-14); busca a partir da raiz
pede pasta restrita (o canário não provou que as regras Read filtram Grep e Glob). No Windows, caminho de rede ou de
dispositivo (`\\\\srv\\c$`, `\\\\?\\UNC\\`, `\\\\?\\Volume{...}`, `\\??\\Volume{...}`, `\\\\wsl.localhost\\`) é negado:
não se sabe se chega à raiz. Raiz: FUNDACAO_RAIZ; sem ela, a da instalação do hook e as pastas abertas (`raizes`).
Barra invertida no padrão (revisão de segurança da 1.7.10, HOOK-F7): o ripgrep a lê como escape (`s\\egredo.txt` é
`segredo.txt`, sem pasta, e desce em todas as subpastas); o filtro do Grep e o padrão do Glob valem também nessa
leitura, e fora do Windows o filtro do Grep com barra invertida é negado. Fora do Windows (HOOK-F8), `/mnt/wslg/` é
negado (`/mnt/wslg/distro` é o disco da distribuição inteiro por outro caminho) e a raiz numa unidade vale também como
`/mnt/<l>/...` (o curinga em `/mnt/*` não passa pela tradução).
Evento ilegível, vazio, campo ausente ou erro: nega.
Limite (honestidade, §0 dos contratos): guarda-corpo das ferramentas de arquivo, não barreira de SO; não percorre a
árvore (ligação abaixo da pasta buscada e vínculo físico passam). O shell lê tudo no Windows e, com a raiz em /mnt/e,
também no Ubuntu (o sandbox não confinou os comandos nas sondas de 31/10/2026). No Windows este hook é o guarda-corpo
principal de leitura das ferramentas; a barreira é o sandbox do Ubuntu onde ele confina (ext4) e o SO.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import sys

FERRAMENTAS = {"Read", "Grep", "Glob"}
NOME_SIMPLES = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?\Z")
MNT = re.compile(r"/+mnt/([A-Za-z])(?=/|\Z)")
UNIDADE = re.compile(r"([A-Za-z]):(?=/|\Z)")
BASH_DO_WINDOWS = re.compile(r"/(?:cygdrive/)?([A-Za-z])(?=/|\Z)")  # Git Bash e Cygwin: só no Windows
DISPOSITIVO = re.compile(r"(?://[?.]/|/\?\?/)(unc/|(?=[a-z]:(?:/|\Z)))", re.IGNORECASE)  # \\?\, \\.\ e \??\
ESPACO_JS = re.compile("[\t\n\x0b\x0c\r \xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+")  # \s do JS
CURTO = re.compile(r"[^.~]{1,6}~[0-9]{1,6}(?:\.[^.]{0,3})?\Z")  # nome curto 8.3 (`progra~1`)
ESCAPE = re.compile(r"\\(.?)", re.S)  # o escape do ripgrep no padrão: a barra sai e o caractere fica (HOOK-F7)
CURINGA = set("*?[]{}(")
DIFICIL = set("[]{}()")  # classe, chaves ou extglob que sobrou: o componente casa qualquer nome (conservador)
LIMITE_EXPANSOES, LIMITE_TEXTO, LIMITE_TRABALHO = 64, 4096, 400_000  # o hook que estoura o prazo (10 s) não bloqueia
_TRABALHO = [0]  # componentes que o _real percorreu nesta decisão (até 256 pedaços × caminho fundo: reconferência)
QUALQUER, OUTRO = "<qualquer>", "<outro>"  # vagas do molde: qualquer nome; qualquer nome menos o projeto


def deny(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


# ------------------------------------------------------------------ caminhos em partes canônicas
def _barras(texto: str) -> str:
    """Barras normais; `\\\\?\\`, `\\\\.\\` e `\\??\\` de unidade saem e os de UNC viram `//`; os outros
    (`\\\\?\\Volume{...}`, `\\\\.\\pipe`) ficam com `//`: rede ou dispositivo."""
    t = texto.replace("\\", "/")
    m = DISPOSITIVO.match(t)
    return ("//" if m.group(1) else "") + t[m.end():] if m else t


def _marca(t: str) -> tuple[str, str]:
    """(marca da raiz do caminho, resto): `e:` para unidade e /mnt/e; `//srv/comp` para rede (só no Windows: nos
    demais, `//` é `/`); `/`; `` se relativo."""
    m = MNT.match(t) or UNIDADE.match(t) or (BASH_DO_WINDOWS.match(t) if os.name == "nt" else None)
    if m:
        return m.group(1).lower() + ":", t[m.end():]
    if os.name == "nt" and t.startswith("//"):
        pedacos = t[2:].split("/", 2)
        return "//" + "/".join(pedacos[:2]).casefold(), (pedacos[2] if len(pedacos) > 2 else "")
    return ("/", t) if t.startswith("/") else ("", t)


def _dividir(texto: str, literal: bool) -> tuple[str, list]:
    """Marca e componentes (original, dobrado, tipo: `lit`, `glob`, `**` ou `..`); `.` some e `..` fica para depois."""
    marca, resto = _marca(_barras(texto))
    comps = []
    for c in resto.split("/"):
        if c in ("", "."):
            continue
        tipo = ".." if c == ".." else "lit" if literal else "**" if "**" in c else "glob" if CURINGA & set(c) else "lit"
        # Windows ignora ponto e espaço no fim do nome e lê `nome:fluxo` dentro de `nome` (conservador no Linux).
        dobrado = c.split(":", 1)[0].rstrip(" .").casefold() if tipo == "lit" else c.casefold()
        if dobrado:
            comps.append((c, dobrado, tipo))
    return marca, comps


def _resolver(marca: str, comps: list) -> tuple[str, list]:
    """`..` resolvido no texto, da esquerda para a direita; `..` depois de `**` não tem leitura simples: recusa."""
    res = []
    for comp in comps:
        if comp[2] != "..":
            res.append(comp)
        elif res and res[-1][2] == "**":
            raise ValueError("`..` depois de `**`")
        elif res:
            res.pop()
    return marca, res


def _nativo(marca: str, origs: list[str]) -> str:
    if len(marca) == 2 and marca.endswith(":"):
        cabeca = marca.upper() + "\\" if os.name == "nt" else "/mnt/" + marca[0] + "/"
    else:
        cabeca = marca.replace("/", os.sep) + os.sep if marca.startswith("//") else os.sep if marca == "/" else ""
    return cabeca + os.sep.join(origs)


def _real(caminho: str) -> str:
    """Caminho real: realpath só do trecho que existe (busca binária), resto igual (o `//` a mais sai no _dividir)."""
    unidade, resto = os.path.splitdrive(caminho)
    partes = [p for p in resto.split(os.sep) if p]
    baixo, alto, cabeca = 0, len(partes), unidade + os.sep
    while baixo < alto:  # o realpath do Windows volta pelo que falta, com duas chamadas ao sistema por componente
        meio = (baixo + alto + 1) // 2
        baixo, alto = (meio, alto) if os.path.lexists(cabeca + os.sep.join(partes[:meio])) else (baixo, meio - 1)
    _TRABALHO[0] += len(partes) * (len(partes).bit_length() + 1)  # o que as lexists e o realpath percorrem, no máximo
    if _TRABALHO[0] > LIMITE_TRABALHO:  # ~1 s no Windows com cache fria (medido: 2,8 milhões levaram 9,5 s)
        raise ValueError(f"caminhos fundos demais para o prazo do hook (mais de {LIMITE_TRABALHO} componentes)")
    return os.sep.join([os.path.realpath(cabeca + os.sep.join(partes[:baixo])), *partes[baixo:]])


def absoluto(texto: str, base: str) -> str:
    """O caminho no formato deste sistema, absoluto a partir de `base` (unidade e /mnt traduzidos; `~` expandido)."""
    t = os.path.expanduser(texto) if texto.startswith("~") else texto
    marca, resto = _marca(_barras(t))
    return os.path.abspath(_nativo(marca, [p for p in resto.split("/") if p]) if marca else os.path.join(base, t))


def formas(texto: str, base: str) -> list[tuple[str, list]]:
    """O caminho literal como escrito (sem ligação resolvida) e o real (ligações e junções resolvidas)."""
    lexico = absoluto(texto, base)
    res = [_resolver(*_dividir(lexico, True))]
    try:
        real = _resolver(*_dividir(_real(lexico), True))
    except (OSError, ValueError):
        real = res[0]
    return res if real == res[0] else res + [real]


def expandir(padrao: str) -> list[str]:
    """Chaves `{a,b}` expandidas (aninhadas inclusive), até LIMITE_EXPANSOES; chave sem vírgula fica como está."""
    pendentes, prontos = [padrao], []
    while pendentes:
        p = pendentes.pop()
        if (opcoes := _grupo(p)) is None:
            prontos.append(p)
        else:
            pendentes.extend(opcoes)
        if len(prontos) + len(pendentes) > LIMITE_EXPANSOES:
            raise ValueError("padrão com chaves demais")
    return prontos


def _grupo(p: str) -> list[str] | None:
    """As opções da chave mais à esquerda que fecha e tem vírgula no próprio nível; None sem ela."""
    pilha, achados = [], []  # uma passada: reexaminar o texto a cada chave aberta custava o quadrado (reconferência)
    for i, ch in enumerate(p):
        if ch == "{":
            pilha.append((i, []))
        elif ch == "," and pilha:
            pilha[-1][1].append(i)
        elif ch == "}" and pilha and (aberta := pilha.pop())[1]:
            achados.append((aberta[0], i, aberta[1]))
    if not achados:
        return None
    ini, fim, virgulas = min(achados)
    return [p[:ini] + p[a + 1:b] + p[fim + 1:] for a, b in zip([ini, *virgulas], [*virgulas, fim])]


def filtros_do_grep(glob: str) -> list[str]:
    """O `glob` do Grep como o Claude Code o passa ao ripgrep, um `--glob` por pedaço: por espaço (o `\\s` do JS) e,
    fora de `{...}`, por vírgula. `!` só exclui: sem pedaço positivo (ou sem pedaço), vale tudo. Mais o inteiro."""
    pedacos = []
    for bruto in ESPACO_JS.split(glob):
        pedacos += [bruto] if "{" in bruto and "}" in bruto else [p for p in bruto.split(",") if p]
    pedacos, total = [p for p in pedacos if p and not p.startswith("!")] or ["**"], 0
    if any((total := total + len(expandir(p))) > 4 * LIMITE_EXPANSOES for p in pedacos):  # longe do prazo do perfil
        raise ValueError("filtro com pedaços ou chaves demais")
    return pedacos + ([glob] if glob.strip() and not glob.startswith("!") and glob not in pedacos else [])


def leituras(padrao: str) -> list[str]:
    """O padrão como o hook o lia (barra invertida = separador) e, com barra invertida, como o ripgrep o lê: escape que
    sai e deixa o caractere (revisão de segurança da 1.7.10, HOOK-F7). Nega quem alcançar numa das duas."""
    return [padrao, ESCAPE.sub(r"\1", padrao)] if "\\" in padrao else [padrao]


def padroes(padrao: str, base: str) -> list[tuple[str, list]]:
    """O padrão (Glob ou pedaço do filtro do Grep) junto da pasta de busca, em cada leitura possível, com a versão
    real do trecho literal do começo (ligações resolvidas)."""
    res = []
    base_marca, base_comps = _dividir(absoluto(base, os.getcwd()), True)
    for p in expandir(padrao):
        p = _barras(os.path.expanduser(p) if p.startswith("~") else p)
        marca, comps = _dividir(p, False)
        leituras = [_resolver(marca, comps)] if marca else []
        if marca in ("", "/"):  # relativo, ou `/` do gitignore (ancorado na pasta de busca)
            if not marca and len(comps) == 1 and comps[0][2] != "**":
                comps = [("**", "**", "**")] + comps  # padrão sem pasta desce em todas as subpastas
            leituras.append(_resolver(base_marca, base_comps + comps))
        for marca_l, comps_l in leituras:
            res.append((marca_l, comps_l))
            n = next((i for i, c in enumerate(comps_l) if c[2] != "lit"), len(comps_l))
            if n:
                real = _resolver(*_dividir(_real(_nativo(marca_l, [c[0] for c in comps_l[:n]])), True))
                if real != (marca_l, comps_l[:n]):
                    res.append((real[0], real[1] + comps_l[n:]))
    return res


# ------------------------------------------------------------------ zonas proibidas
def _casa(comp, vaga, projeto, curto: bool) -> bool:
    _, dobrado, tipo = comp
    if vaga == QUALQUER or (curto and tipo == "lit" and CURTO.match(dobrado)):
        return True
    if vaga == OUTRO:
        return tipo != "lit" or projeto is None or dobrado != projeto
    if tipo == "lit":
        return dobrado == vaga
    return bool(DIFICIL & set(dobrado)) or fnmatch.fnmatchcase(vaga, dobrado)


def alcanca(caminho: tuple[str, list], molde: tuple[str, list], projeto: str | None) -> bool:
    """O caminho (ou padrão) pode casar algo dentro do molde, ou o próprio molde? Fora do Windows, nome curto 8.3 numa
    unidade (`/mnt/e/PROJET~1`) casa qualquer nome: o DrvFs o resolve e o caminho real não o expande."""
    marca, comps = caminho
    if marca != molde[0]:
        return False
    curto = os.name != "nt" and marca.endswith(":")
    vagas, j = molde[1], 0
    for comp in comps:
        if j == len(vagas) or comp[2] == "**":
            return True
        if not _casa(comp, vagas[j], projeto, curto):
            return False
        j += 1
    return j == len(vagas)


def projeto_da_sessao(env: dict) -> str | None:
    p = (env.get("FUNDACAO_PROJECT") or "").strip()
    return p.casefold() if NOME_SIMPLES.fullmatch(p) and ".." not in p else None


def _corte(comps: list, de: int = 0) -> int:
    return max((k for k in range(de, len(comps)) if comps[k][1] == "projects"), default=len(comps))


def raizes(env: dict, cwd: str) -> list[tuple[str, list]]:
    """As formas da raiz: FUNDACAO_RAIZ; sem ela, a pasta da instalação (§7: `<raiz>/.claude/hooks/`; a sessão não a
    escolhe), inteira se tiver projects/<projeto da sessão>, e CLAUDE_PROJECT_DIR e o cwd, cada uma cortada no último
    `projects` (o de dentro da raiz da instalação, se dentro dela; a raiz pode estar em ~/projects/: reconferência)."""
    if explicita := (env.get("FUNDACAO_RAIZ") or "").strip():
        return formas(explicita, cwd)
    hooks, instalada = os.path.dirname(os.path.abspath(__file__)), []
    if [os.path.basename(p).casefold() for p in (hooks, os.path.dirname(hooks))] == ["hooks", ".claude"]:
        pasta, nome = os.path.dirname(os.path.dirname(hooks)), (env.get("FUNDACAO_PROJECT") or "").strip()
        inteira = projeto_da_sessao(env) is not None and os.path.lexists(os.path.join(pasta, "projects", nome))
        instalada = [(m, c if inteira else c[:_corte(c)]) for m, c in formas(pasta, cwd)]
    res = list(instalada)
    for texto in filter(None, (env.get("CLAUDE_PROJECT_DIR"), cwd)):
        for marca, comps in formas(texto, cwd):
            dobrados = [c[1] for c in comps]
            de = next((len(r) for m, r in instalada if m == marca and dobrados[:len(r)] == [c[1] for c in r]), 0)
            res.append((marca, comps[:_corte(comps, de)]))
    return res


def zonas(env: dict, cwd: str, projeto: str | None) -> list[tuple[str, tuple[str, list]]]:
    res = []
    for marca, comps in raizes(env, cwd):
        dobrados = [c[1] for c in comps]
        # No Windows (NTFS, sem caixa), sem projects/<projeto>/data não há dado próprio a proteger; nos demais, vale.
        dados = env.get("FUNDACAO_SEM_DADOS") == "1" and (os.name != "nt" or projeto is None or os.path.lexists(
            os.path.join(_nativo(marca, [c[0] for c in comps]), "projects", projeto, "data")))
        # Revisão de segurança da 1.7.10, HOOK-F8: fora do Windows, a raiz numa unidade é também /mnt/<l>/... (o
        # curinga em `/mnt/*` não passa pela tradução para `<l>:`).
        unidade = os.name != "nt" and len(marca) == 2 and marca[1] == ":"
        outras = [("/", ["mnt", marca[0]] + dobrados)] if unidade else []
        for m, d in [(marca, dobrados)] + outras:
            res.append(("state/ da fundação", (m, d + ["state"])))
            res.append(("outro projeto" if projeto else "projects/ sem projeto da sessão (FUNDACAO_PROJECT)",
                        (m, d + ["projects", OUTRO])))
            if dados:
                res.append(("pasta de dados (FUNDACAO_SEM_DADOS=1)", (m, d + ["projects", QUALQUER, "data"])))
    if os.name != "nt":  # HOOK-F8: /mnt/wslg/distro é o disco da distribuição inteiro (WSLg), outro nome da raiz
        res.append(("/mnt/wslg (apelido do disco da distribuição)", ("/", ["mnt", "wslg"])))
    return res


# ------------------------------------------------------------------ decisão
def decide(event: dict, env: dict) -> dict | None:
    tool, _TRABALHO[0] = event.get("tool_name"), 0
    if not isinstance(tool, str) or not tool:
        return deny("evento sem nome de ferramenta: negado por segurança")
    if tool not in FERRAMENTAS:
        return None
    entrada = event.get("tool_input")
    cwd = event.get("cwd") if isinstance(event.get("cwd"), str) and event.get("cwd") else os.getcwd()
    if not isinstance(entrada, dict):
        return deny(f"{tool} sem entrada legível: negado")
    alvo = entrada.get("file_path" if tool == "Read" else "path")
    filtro = None if tool == "Read" else entrada.get("glob" if tool == "Grep" else "pattern")
    if tool == "Read" and (not isinstance(alvo, str) or not alvo):
        return deny("Read sem caminho (file_path): negado")
    if tool != "Read" and alvo is not None and not isinstance(alvo, str):
        return deny(f"{tool} com pasta ilegível (path): negado")
    if tool == "Glob" and (not isinstance(filtro, str) or not filtro):
        return deny("Glob sem padrão (pattern): negado")
    if filtro is not None and not isinstance(filtro, str):
        return deny("Grep com filtro ilegível (glob): negado")
    if any(isinstance(t, str) and len(t) > LIMITE_TEXTO for t in (alvo, filtro, cwd)):  # longe do prazo do perfil
        return deny(f"{tool} com caminho ou padrão acima de {LIMITE_TEXTO} caracteres: negado")
    if tool == "Grep" and os.name != "nt" and "\\" in (filtro or ""):  # revisão de segurança da 1.7.10, HOOK-F7
        return deny("guarda_leitura (guarda-corpo): filtro (glob) do Grep com barra invertida negado fora do Windows: "
                    "o ripgrep a lê como escape (s\\egredo.txt é segredo.txt, sem pasta, e desce em todas as "
                    "subpastas). Use / como separador e um padrão com pasta.")
    try:
        filtros = [] if tool == "Read" else [filtro] if tool == "Glob" else filtros_do_grep(filtro or "")
        textos = [alvo or ""] + filtros
        if any("\x00" in t for t in textos + [cwd]):
            return deny(f"{tool} com caractere nulo no caminho: negado")
        # O `/??/` que sobra do _barras (`\??\Volume{...}`, `\??\GLOBALROOT`) é dispositivo do NT; o cwd também conta.
        if os.name == "nt" and any(_barras(t).startswith(("//", "/??/")) for t in textos + [cwd]):
            return deny(f"guarda_leitura (guarda-corpo): {tool} com caminho de rede ou de dispositivo (\\\\srv\\..., "
                        "\\\\?\\UNC\\..., \\\\?\\Volume{...}, \\\\wsl.localhost\\...) negado no Windows: não se sabe "
                        "se ele chega a outro projeto ou a state/. Use o caminho pela unidade (E:\\...).")
        candidatos = (formas(alvo, cwd) if tool == "Read"
                      else [c for f in filtros for g in leituras(f) for c in padroes(g, absoluto(alvo or cwd, cwd))])
    except ValueError as exc:  # chaves ou pedaços demais, `..` depois de `**`: sem leitura simples, nega
        return deny(f"guarda_leitura: padrão sem leitura simples ({exc}): negado; use um padrão mais simples")
    projeto = projeto_da_sessao(env)
    for rotulo, molde in zonas(env, cwd, projeto):
        if any(alcanca(c, molde, projeto) for c in candidatos):
            return deny(_motivo(tool, rotulo, env))
    return None


def _motivo(tool: str, rotulo: str, env: dict) -> str:
    projeto = (env.get("FUNDACAO_PROJECT") or "").strip() or "<projeto>"
    acao = f"leitura em {rotulo} negada" if tool == "Read" else (
        f"a busca do {tool} pode alcançar {rotulo}: restrinja `path` a projects/{projeto}/ (ou a uma pasta fora de "
        "projects/ e de state/) e use um padrão com pasta (padrão sem pasta desce em todas as subpastas)")
    return (f"guarda_leitura (guarda-corpo): {acao}. Dado de outro projeto ou da fundação só pelo serviço da "
            "fundação (python -m fundacao ...), com a identidade do lançador.")


def _estrito(pares):  # object_pairs_hook e parse_constant: chave repetida, NaN e Infinity recusados
    if isinstance(pares, str) or len({chave for chave, _ in pares}) != len(pares):
        raise ValueError("entrada inválida")
    return dict(pares)


def main() -> int:
    try:
        # Bytes em UTF-8: com -I o Python ignora PYTHONUTF8 e leria a entrada na página de código do Windows.
        event = json.loads(sys.stdin.buffer.read().decode("utf-8"), object_pairs_hook=_estrito, parse_constant=_estrito)
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
