#!/usr/bin/env python3
r"""Preparo do host da fundação para dados reais: perfis do Claude Code gerados pelos modelos da skill, o
`/etc/wsl.conf` com um só bloco [interop] desligado e o lançador da sessão de dados reais no WSL2.

Na implantação de 2026-10-20 o perfil do WSL levou três versões (v1: `state/` virou tmpfs vazio no sandbox, porque
`Read(./state/**)` também vira `denyRead`; v2: só leitura; v3: leitura e escrita) e hooks e perfis foram copiados à
mão. Aqui os perfis saem dos modelos `windows/settings.json` e `wsl/settings.wsl.json` com os caminhos da máquina.
Chamado por `windows/preparar-maquina.ps1` e `wsl/preparar-wsl.sh`. Só grava com `--saida`; de `projects/` lê só os
nomes do primeiro nível (para negar, no sandbox, a escrita nos outros projetos). Biblioteca padrão.

  python preparo_host.py perfil-windows --raiz <raiz> --python <python.exe> [--negar-skill <nome>]...
         [--saida <arquivo>]
  python preparo_host.py perfil-wsl --raiz <raiz> --projeto <id> --perfil-windows <C:\Users\nome>
         [--backups <pasta>]... [--somente-leitura <pasta>]... [--ancora-base <pasta>] [--negar-skill <nome>]...
         [--saida <arquivo>]
  python preparo_host.py identidade --titular <id> [--projeto <id>] [--atual <settings.local.json>] [--estrito]
         [--saida <arquivo>]
  python preparo_host.py wsl-conf --arquivo <wsl.conf> [--saida <arquivo>]     (JSON com "mudou" e "texto")
  python preparo_host.py conferir-perfil-wsl --perfil <settings.wsl.json> --raiz <raiz> --projeto <id>
  python preparo_host.py conferir-identidade --arquivo <settings.local.json> --titular <id> --projeto <id>
  python preparo_host.py lancador --raiz <raiz> --projeto <id> --titular <id> --claude <binário> --claude-versao <v>
         --claude-sha256 <hash> --origem-hash <texto> --skill-md <SKILL.md> --saida <arquivo | ->
Pastas de dados não viram instrução (análise do vibe-coding-toolkit, 21/10/2026, propostas 2 e 3): os dois perfis
trazem `claudeMdExcludes` para `**/projects/*/data/**` (CLAUDE.md, AGENTS.md e rules de uma cópia importada não
carregam); skill aninhada, que nenhuma configuração exclui, sai em `permissions.deny` como `Skill(<nome>)` com
`--negar-skill` (nomes do `instrucoes_aninhadas.py` da skill); e o perfil de dados reais nega `WebFetch` e
`WebSearch`, a saída que o sandbox de rede não cobre. `identidade --projeto` entrega também o projeto
autenticado das sessões (`FUNDACAO_PROJECT`), que o guarda de escrita exige.
O preparo do WSL só fixa o que conferiu inteiro (auditoria Codex Security da 1.7.6, #5): `conferir-perfil-wsl` gera
de novo, pelo modelo, o perfil com as vagas lidas dele (perfil do Windows, âncora, backups, pastas só de leitura,
skills negadas) e compara tudo, e cada projeto da raiz, menos o da sessão, tem de estar negado; `conferir-identidade`
aceita no `settings.local.json`, que a sessão carrega inteiro, só a identidade do titular informado e o projeto;
`lancador` repete as conferências (perfil, hooks iguais aos da skill e identidade) nos mesmos bytes cujo SHA-256 fixa.
Códigos: 0 ok · 1 conferência com problemas ou conflito (nada gravado) · 2 uso incorreto ou entrada
inválida (nada gravado).
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import ntpath
import posixpath
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
MODELO_WINDOWS = AQUI / "windows" / "settings.json"
MODELO_WSL = AQUI / "wsl" / "settings.wsl.json"
MODELO_LANCADOR = AQUI / "wsl" / "abrir-sessao.sh"
MODELO_HOOKS = AQUI.parent / "hooks"  # os hooks da skill, que o preparo do Windows copia para <raiz>/.claude/hooks
HOOKS = ("guarda_caminho.py", "guarda_identidade.py")
ANCORA_BASE_WSL = "/mnt/c/ProgramData/FundacaoIA"  # a pasta da âncora do Windows (allowed_signers), vista do WSL
MONTAGEM = "/mnt/"  # [automount] root padrão do WSL
IDENTIFICADOR = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MARCADOR = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
BARRA_INVERTIDA = chr(92)
CHAVE_IDENTIDADE = "FUNDACAO_" + "PRINCIPAL"  # a variável que o lançador entrega às sessões
CHAVE_PROJETO = "FUNDACAO_PROJECT"  # projeto autenticado das sessões (guarda_caminho: escrita só nele)
NOME_DE_SKILL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
EXCLUSAO_DE_DADOS = "**/projects/*/data/**"
CHAVES_DO_LANCADOR = ("RAIZ", "PROJETO", "TITULAR", "CLAUDE_BIN", "CLAUDE_VERSAO", "CLAUDE_SHA256",
                      "CLAUDE_ORIGEM_HASH", "PERFIL_SHA256", "HOOK_CAMINHO_SHA256", "HOOK_IDENTIDADE_SHA256",
                      "LOCAL_SHA256", "SKILL_MD")


class EntradaInvalida(ValueError):
    pass


class Conflito(EntradaInvalida):
    """Arquivo do titular com valor diferente do pedido: não é sobrescrito."""


def identificador(valor: str, rotulo: str) -> str:
    if not isinstance(valor, str) or not IDENTIFICADOR.match(valor) or ".." in valor:
        raise EntradaInvalida(f"{rotulo} inválido: {valor!r} (use letras minúsculas, dígitos, '.', '_' ou '-')")
    return valor


def caminho_wsl(caminho: str, montagem: str = MONTAGEM) -> str:
    """Unidade do Windows (`E:` e o resto, com qualquer barra) vira `/mnt/e/...`; caminho absoluto do Linux fica
    igual, sem a barra final. Relativo e caminho de rede são recusados."""
    texto = str(caminho).strip()
    m = re.match(r"^([A-Za-z]):([/\x5c].*)?$", texto)
    if m:
        resto = re.sub(r"[/\x5c]+", "/", m.group(2) or "").strip("/")
        return montagem.rstrip("/") + "/" + m.group(1).lower() + ("/" + resto if resto else "")
    if texto.startswith("/") and not texto.startswith("//"):
        return texto.rstrip("/") or "/"
    raise EntradaInvalida(f"caminho absoluto esperado (unidade do Windows ou caminho do Linux): {caminho!r}")


def texto_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def renderizar(modelo, valores: dict, listas: dict | None = None):
    """Troca `{{NOME}}` pelos valores. Item de lista com um marcador de `listas` vira um item por valor (nenhum, se
    a lista estiver vazia). Sobrou marcador = erro: o perfil nunca sai pela metade."""
    listas = listas or {}

    def texto(s: str) -> str:
        def troca(m):
            if m.group(1) not in valores:
                raise EntradaInvalida(f"marcador sem valor no modelo: {m.group(0)}")
            return str(valores[m.group(1)])
        return MARCADOR.sub(troca, s)

    def passo(no):
        if isinstance(no, dict):
            return {k: passo(v) for k, v in no.items()}
        if isinstance(no, list):
            saida = []
            for item in no:
                nomes = MARCADOR.findall(item) if isinstance(item, str) else []
                de_lista = [n for n in nomes if n in listas]
                if len(de_lista) > 1:
                    raise EntradaInvalida(f"item com dois marcadores de lista: {item}")
                if de_lista:
                    marca = "{{" + de_lista[0] + "}}"
                    saida.extend(texto(item.replace(marca, valor)) for valor in listas[de_lista[0]])
                else:
                    saida.append(passo(item))
            return saida
        return texto(no) if isinstance(no, str) else no

    saida = passo(copy.deepcopy(modelo))
    sobras = [s for s in _textos(saida) if "{{" in s or "}}" in s]
    if sobras:
        raise EntradaInvalida(f"marcador não substituído no modelo: {sobras[0][:120]}")
    return saida


def _textos(no):
    if isinstance(no, dict):
        for v in no.values():
            yield from _textos(v)
    elif isinstance(no, list):
        for v in no:
            yield from _textos(v)
    elif isinstance(no, str):
        yield no


def ler_modelo(caminho: Path) -> dict:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def negar_skills(perfil: dict, nomes=()) -> dict:
    """Acrescenta `Skill(<nome>)` às negações (skill aninhada em pasta de dados: nenhuma configuração a exclui)."""
    negacoes = perfil.setdefault("permissions", {}).setdefault("deny", [])
    for nome in nomes:
        if not NOME_DE_SKILL.match(str(nome)):
            raise EntradaInvalida(f"nome de skill inválido: {nome!r}")
        if f"Skill({nome})" not in negacoes:
            negacoes.append(f"Skill({nome})")
    return perfil


def perfil_windows(*, raiz: str, python: str, modelo: dict | None = None, negar=()) -> dict:
    """`.claude/settings.json` da raiz (sessões do Windows): negações, MCP do aplicativo e os dois hooks."""
    if not ntpath.isabs(str(raiz)) or not ntpath.isabs(str(python)):
        raise EntradaInvalida("raiz e python precisam ser caminhos absolutos do Windows")
    raiz, python = ntpath.normpath(str(raiz)), ntpath.normpath(str(python))  # barras do Windows nos caminhos
    pasta = ntpath.join(raiz, ".claude", "hooks")
    valores = {"PYTHON": python, "HOOK_CAMINHO": ntpath.join(pasta, "guarda_caminho.py"),
               "HOOK_IDENTIDADE": ntpath.join(pasta, "guarda_identidade.py")}
    return negar_skills(renderizar(modelo or ler_modelo(MODELO_WINDOWS), valores), negar)


def perfil_wsl(*, raiz: str, projeto: str, perfil_windows: str, outros_projetos, backups=(), somente_leitura=(),
               ancora_base: str = ANCORA_BASE_WSL, montagem: str = MONTAGEM, modelo: dict | None = None,
               negar=()) -> dict:
    """`.claude/settings.wsl.json` (sessão de dados reais no WSL2, sandbox estrito): `state/` legível e gravável
    pelos comandos do sandbox e negado à ferramenta Read; escrita negada nos outros projetos, na área do titular
    (`.claude`), na pasta da âncora e nas pastas só de leitura."""
    identificador(projeto, "projeto")
    outros = sorted({identificador(p, "projeto") for p in outros_projetos})
    if projeto in outros:
        raise EntradaInvalida(f"o projeto da sessão ({projeto}) não pode estar entre os projetos negados")
    raiz_wsl = caminho_wsl(raiz, montagem)
    perfil = _montar_perfil_wsl(raiz_wsl, caminho_wsl(perfil_windows, montagem), caminho_wsl(ancora_base, montagem),
                                outros, [caminho_wsl(b, montagem) for b in backups],
                                [caminho_wsl(s, montagem) for s in somente_leitura], negar, modelo)
    problemas = invariantes_perfil_wsl(perfil, raiz_wsl)
    if problemas:
        raise EntradaInvalida("o modelo do perfil do WSL não garante: " + "; ".join(problemas))
    return perfil


def _montar_perfil_wsl(raiz_wsl: str, perfil_windows: str, ancora_base: str, outros, backups, somente_leitura,
                       negar, modelo: dict | None = None) -> dict:
    """O modelo do WSL preenchido com caminhos já no formato do WSL (para gerar e para conferir)."""
    valores = {"RAIZ": raiz_wsl, "PERFIL_WINDOWS": perfil_windows, "ANCORA_BASE": ancora_base,
               "HOOK_CAMINHO": raiz_wsl + "/.claude/hooks/guarda_caminho.py",
               "HOOK_IDENTIDADE": raiz_wsl + "/.claude/hooks/guarda_identidade.py"}
    listas = {"OUTROS_PROJETOS": list(outros), "BACKUPS": list(backups), "SOMENTE_LEITURA": list(somente_leitura)}
    return negar_skills(renderizar(modelo or ler_modelo(MODELO_WSL), valores, listas), negar)


def projetos_da_raiz(raiz) -> list[str]:
    """Nomes das pastas no primeiro nível de `projects/` (sem entrar nelas e sem pastas ocultas)."""
    pasta = Path(raiz) / "projects"
    if not pasta.is_dir():
        return []
    return sorted(p.name for p in pasta.iterdir() if p.is_dir() and not p.name.startswith("."))


def identidade(titular: str, atual: dict | None = None, projeto: str | None = None, estrito: bool = False) -> dict:
    """`.claude/settings.local.json`: a identidade das sessões vem do lançador (regime de dados reais). Com o
    arquivo atual, acrescenta só a identidade e mantém o resto; outra identidade já gravada é `Conflito`. Com
    `estrito` (o preparo do Windows com -Projeto), sai só a identidade e o projeto: a sessão de dados reais do WSL
    carrega o arquivo inteiro e só aceita isso (`conferir_identidade`)."""
    identificador(titular, "titular")
    novo = copy.deepcopy(atual) if isinstance(atual, dict) else {}
    env = novo.setdefault("env", {})
    if not isinstance(env, dict):
        raise EntradaInvalida("settings.local.json com 'env' que não é objeto")
    existente = env.get(CHAVE_IDENTIDADE)
    if existente not in (None, titular):
        raise Conflito(f"settings.local.json já entrega a identidade {existente!r}, não {titular!r}: só o titular "
                       f"decide a troca")
    env[CHAVE_IDENTIDADE] = titular
    if projeto is not None:
        identificador(projeto, "projeto")
        if env.get(CHAVE_PROJETO) not in (None, projeto):
            raise Conflito(f"settings.local.json já entrega o projeto {env[CHAVE_PROJETO]!r}, não {projeto!r}: só o "
                           f"titular decide a troca")
        env[CHAVE_PROJETO] = projeto
    if estrito:
        novo = {"env": {k: env[k] for k in (CHAVE_IDENTIDADE, CHAVE_PROJETO) if k in env}}
    return novo


def conferir_identidade(dados, titular: str, projeto: str | None = None) -> list[str]:
    """`settings.local.json` da sessão de dados reais (`--setting-sources local`): só `env` com a identidade do
    titular e, se houver, o projeto da sessão. Hook, permissão, plugin, sandbox ou variável a mais (como
    FUNDACAO_PERMITIR_TROCA_IDENTIDADE) mudariam a sessão por fora do perfil fixado [Decisão; auditoria Codex Security
    da 1.7.6, #5]. Das chaves a mais sai só o nome; valor só sai se for um identificador."""
    identificador(titular, "titular")
    if not isinstance(dados, dict):
        return ["settings.local.json não é um objeto JSON"]

    def mostrar(valor) -> str:
        return repr(valor) if isinstance(valor, str) and IDENTIFICADOR.match(valor) else "(ausente ou fora do formato)"

    problemas = []
    extras = sorted(str(k) for k in dados if k != "env")
    if extras:
        problemas.append("chaves além da identidade: " + ", ".join(extras))
    env = dados.get("env")
    if not isinstance(env, dict):
        return problemas + ["sem o objeto env com a identidade"]
    extras = sorted(str(k) for k in env if k not in (CHAVE_IDENTIDADE, CHAVE_PROJETO))
    if extras:
        problemas.append("variáveis além da identidade em env: " + ", ".join(extras))
    if env.get(CHAVE_IDENTIDADE) != titular:
        problemas.append(f"a identidade entregue é {mostrar(env.get(CHAVE_IDENTIDADE))}, não a do titular {titular!r}")
    if CHAVE_PROJETO in env and env[CHAVE_PROJETO] != projeto:
        problemas.append(f"o projeto entregue é {mostrar(env[CHAVE_PROJETO])}, não o da sessão ({projeto!r})")
    return problemas


def _objeto(valor) -> dict:
    return valor if isinstance(valor, dict) else {}


def _lista(valor) -> list:
    return valor if isinstance(valor, list) else []


def invariantes_perfil_wsl(perfil, raiz_wsl: str) -> list[str]:
    """O que o caso real provou (sandbox estrito com `state/` utilizável e a área do titular protegida) e a rede
    fechada. Vale para o modelo, ao gerar, e para o perfil, ao conferir."""
    problemas = []
    perfil = _objeto(perfil)
    sandbox = _objeto(perfil.get("sandbox"))
    fs = _objeto(sandbox.get("filesystem"))
    state = raiz_wsl.rstrip("/") + "/state"
    if sandbox.get("enabled") is not True or sandbox.get("failIfUnavailable") is not True:
        problemas.append("sandbox desligado ou sem falha obrigatória (failIfUnavailable)")
    if sandbox.get("allowUnsandboxedCommands") is not False:
        problemas.append("comandos fora do sandbox permitidos (allowUnsandboxedCommands)")
    if state not in _lista(fs.get("allowRead")):
        problemas.append("state/ sem leitura no sandbox (v1: tmpfs vazio, com banco falso)")
    if state not in _lista(fs.get("allowWrite")):
        problemas.append("state/ sem escrita no sandbox (v2: só leitura)")
    if raiz_wsl.rstrip("/") + "/.claude" not in _lista(fs.get("denyWrite")):
        problemas.append(".claude da raiz gravável pelo sandbox")
    if _objeto(sandbox.get("network")).get("allowedDomains") != []:
        problemas.append("rede do sandbox aberta: sandbox.network.allowedDomains tem de ficar vazio")
    negacoes = [n for n in _lista(_objeto(perfil.get("permissions")).get("deny")) if isinstance(n, str)]
    if "Read(./state/**)" not in negacoes:
        problemas.append("ferramenta Read com acesso a state/")
    if not {"WebFetch", "WebSearch"} <= set(negacoes):
        problemas.append("WebFetch e WebSearch liberados: saída de dados que o sandbox de rede não cobre")
    if EXCLUSAO_DE_DADOS not in _lista(perfil.get("claudeMdExcludes")):
        problemas.append("instruções de pastas de dados (CLAUDE.md, AGENTS.md) carregáveis: falta claudeMdExcludes")
    comandos = [_objeto(h) for g in _lista(_objeto(perfil.get("hooks")).get("PreToolUse"))
                for h in _lista(_objeto(g).get("hooks"))]
    esperados = {raiz_wsl.rstrip("/") + "/.claude/hooks/" + n for n in HOOKS}
    if not esperados <= {a for h in comandos for a in _lista(h.get("args")) if isinstance(a, str)}:
        problemas.append("hooks guarda_caminho e guarda_identidade da raiz ausentes")
    return problemas


def _caminho_de_vaga(caminho) -> bool:
    """Caminho absoluto do Linux, normalizado, sem curinga nem quebra de linha (como o gerador o escreve)."""
    return (isinstance(caminho, str) and caminho.startswith("/") and not caminho.startswith("//")
            and posixpath.normpath(caminho) == caminho and not any(c in caminho for c in "*?\n\r\0"))


def parametros_do_perfil_wsl(perfil, raiz_wsl: str) -> dict:
    """As vagas do modelo como estão no perfil (perfil do Windows, pasta da âncora, pastas só de leitura, backups,
    outros projetos e skills negadas), para gerar de novo e comparar. Fora do formato do modelo: EntradaInvalida."""
    raiz = raiz_wsl.rstrip("/")
    perfil = _objeto(perfil)
    fs = _objeto(_objeto(perfil.get("sandbox")).get("filesystem"))
    negacoes = _lista(_objeto(perfil.get("permissions")).get("deny"))
    janelas = [c for c in _lista(fs.get("denyRead"))
               if isinstance(c, str) and c.startswith("/") and c.endswith("/.ssh")]
    if len(janelas) != 1 or "Edit(./.claude/**)" not in negacoes:
        raise EntradaInvalida("perfil fora do formato do modelo (credenciais do Windows ou área do titular)")
    resto = negacoes[negacoes.index("Edit(./.claude/**)") + 1:]
    edicoes = []
    for regra in resto:  # Edit(/<âncora>/**) e um Edit(/<pasta>/**) por pasta só de leitura
        if not (isinstance(regra, str) and regra.startswith("Edit(/") and regra.endswith("/**)")):
            break
        edicoes.append(regra[len("Edit(/"):-len("/**)")])
    if not edicoes:
        raise EntradaInvalida("perfil fora do formato do modelo (pasta da âncora)")
    somente_leitura = edicoes[1:]
    negados = _lista(fs.get("denyWrite"))  # .claude, os outros projetos, as pastas só de leitura e a âncora
    prefixo = raiz + "/projects/"
    meio = negados[1:len(negados) - len(somente_leitura) - 1]
    if len(negados) < 2 + len(somente_leitura) or not all(isinstance(c, str) and c.startswith(prefixo) for c in meio):
        raise EntradaInvalida("perfil fora do formato do modelo (escrita negada fora da ordem do modelo)")
    vagas = {"perfil_windows": janelas[0][:-len("/.ssh")], "ancora_base": edicoes[0],
             "somente_leitura": somente_leitura,
             "backups": [c for c in _lista(fs.get("allowWrite")) if c != raiz + "/state"],
             "outros_projetos": [c[len(prefixo):] for c in meio],
             "negar": [r[len("Skill("):-1] for r in resto[len(edicoes):]
                       if isinstance(r, str) and r.startswith("Skill(") and r.endswith(")")]}
    for caminho in [vagas["perfil_windows"], vagas["ancora_base"], *somente_leitura, *vagas["backups"]]:
        if not _caminho_de_vaga(caminho):
            raise EntradaInvalida(f"caminho fora do formato do modelo no perfil: {caminho!r}")
    for nome in vagas["outros_projetos"]:
        identificador(nome, "projeto negado no perfil")
    return vagas


def _canonico(valor) -> str:
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _primeira_diferenca(atual, esperado, caminho: str = "") -> str:
    """Onde o perfil difere do esperado (só o caminho das chaves, sem valores)."""
    if isinstance(atual, dict) and isinstance(esperado, dict):
        for k in sorted(set(atual) | set(esperado), key=str):
            if k not in esperado:
                return f"{caminho}{k} (a mais)"
            if k not in atual:
                return f"{caminho}{k} (falta)"
            if _canonico(atual[k]) != _canonico(esperado[k]):
                return _primeira_diferenca(atual[k], esperado[k], f"{caminho}{k}.")
    elif isinstance(atual, list) and isinstance(esperado, list) and len(atual) == len(esperado):
        for i, (x, y) in enumerate(zip(atual, esperado)):
            if _canonico(x) != _canonico(y):
                return _primeira_diferenca(x, y, f"{caminho.rstrip('.')}[{i}].")
    return caminho.rstrip(".") or "(perfil inteiro)"


def conferir_perfil_wsl(perfil, raiz_wsl: str, projeto: str | None = None, outros_projetos=None) -> list[str]:
    """O perfil do WSL que o preparo fixa: os invariantes do caso real e, inteiro, igual ao que o modelo gera com as
    vagas lidas dele [Decisão; auditoria Codex Security da 1.7.6, #5: antes, só alguns indicadores eram olhados e
    rede, credenciais, outros projetos, matcher, comando e falha fechada dos hooks e chaves a mais passavam]. Com
    `outros_projetos` (os da raiz), cada um deles tem de estar negado; com `projeto`, o da sessão não pode estar."""
    raiz_wsl = raiz_wsl.rstrip("/")
    problemas = invariantes_perfil_wsl(perfil, raiz_wsl)
    try:
        vagas = parametros_do_perfil_wsl(perfil, raiz_wsl)
        esperado = _montar_perfil_wsl(raiz_wsl, vagas["perfil_windows"], vagas["ancora_base"],
                                      vagas["outros_projetos"], vagas["backups"], vagas["somente_leitura"],
                                      vagas["negar"])
    except EntradaInvalida as exc:
        return problemas + [str(exc)]
    if _canonico(perfil) != _canonico(esperado):
        problemas.append("perfil diferente do que o modelo da skill gera para esta raiz (primeira diferença: "
                         f"{_primeira_diferenca(perfil, esperado)})")
    if outros_projetos is not None:
        faltam = sorted(set(outros_projetos) - set(vagas["outros_projetos"]) - {projeto})
        if faltam:
            problemas.append("projetos da raiz sem escrita negada no perfil (criados depois do preparo do Windows?): "
                             + ", ".join(faltam))
    if projeto is not None and projeto in vagas["outros_projetos"]:
        problemas.append(f"o projeto da sessão ({projeto}) está entre os projetos com escrita negada")
    return problemas


def ajustar_wsl_conf(texto: str) -> tuple[str, bool]:
    """Um único bloco `[interop]` com `enabled=false` e `appendWindowsPath=false`; o resto do arquivo fica igual.
    Blocos `[interop]` repetidos (no caso real, três) viram um, com as outras chaves do primeiro em que aparecem."""
    original = texto
    linhas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if linhas and linhas[-1] == "":
        linhas.pop()
    preambulo, secoes = [], []  # secoes: [nome em minúsculas, linha do cabeçalho, corpo]
    for linha in linhas:
        m = re.match(r"^\s*\[([^\]]+)\]\s*$", linha)
        if m:
            secoes.append([m.group(1).strip().lower(), linha, []])
        elif secoes:
            secoes[-1][2].append(linha)
        else:
            preambulo.append(linha)

    def chave(linha: str) -> str | None:
        m = re.match(r"^\s*([A-Za-z0-9_.-]+)\s*=", linha)
        return m.group(1).lower() if m else None

    interop = [s for s in secoes if s[0] == "interop"]
    if not interop:
        if (preambulo or secoes) and (secoes[-1][2] if secoes else preambulo)[-1:] != [""]:
            (secoes[-1][2] if secoes else preambulo).append("")
        secoes.append(["interop", "[interop]", []])
        interop = [secoes[-1]]
    primeira = interop[0]
    vistas = {chave(l) for l in primeira[2] if chave(l)}
    for repetida in interop[1:]:
        for linha in repetida[2]:
            k = chave(linha)
            if k and k not in vistas:
                primeira[2].append(linha)
                vistas.add(k)
        secoes.remove(repetida)
    corpo, presentes = [], set()
    for linha in primeira[2]:
        k = chave(linha)
        if k in ("enabled", "appendwindowspath"):
            presentes.add(k)
            if linha.split("=", 1)[1].strip().lower() != "false":
                linha = ("enabled" if k == "enabled" else "appendWindowsPath") + "=false"
        corpo.append(linha)
    fim = len(corpo)
    while fim and not corpo[fim - 1].strip():
        fim -= 1
    faltam = [n + "=false" for n, k in (("enabled", "enabled"), ("appendWindowsPath", "appendwindowspath"))
              if k not in presentes]
    primeira[2] = corpo[:fim] + faltam + corpo[fim:]
    saida = list(preambulo)
    for _nome, cabecalho, corpo_secao in secoes:
        saida.append(cabecalho)
        saida.extend(corpo_secao)
    while saida and not saida[-1].strip():
        saida.pop()
    novo = "\n".join(saida) + "\n"
    return novo, novo != original


def _aspas_bash(valor: str) -> str:
    return valor.replace("'", "'" + BARRA_INVERTIDA + "''")


def lancador(valores: dict, modelo: str | None = None) -> str:
    """`abrir-sessao.sh` com os valores fixados. Cada marcador do modelo fica entre aspas simples, e o valor tem as
    aspas simples escapadas: um caminho com aspas ou espaços não vira comando."""
    faltam = [k for k in CHAVES_DO_LANCADOR if not str(valores.get(k, "")).strip()]
    if faltam:
        raise EntradaInvalida("valores ausentes para o lançador: " + ", ".join(faltam))
    for k in CHAVES_DO_LANCADOR:
        if any(c in str(valores[k]) for c in ("\n", "\r", "\0")):
            raise EntradaInvalida(f"{k} com quebra de linha")
    for k in ("RAIZ", "CLAUDE_BIN", "SKILL_MD"):
        if not str(valores[k]).startswith("/"):
            raise EntradaInvalida(f"{k} precisa ser caminho absoluto do Linux: {valores[k]!r}")
    for k in ("CLAUDE_SHA256", "PERFIL_SHA256", "HOOK_CAMINHO_SHA256", "HOOK_IDENTIDADE_SHA256", "LOCAL_SHA256"):
        if not SHA256.match(str(valores[k])):
            raise EntradaInvalida(f"{k} não é um SHA-256 em hexadecimal minúsculo: {valores[k]!r}")
    identificador(str(valores["PROJETO"]), "projeto")
    identificador(str(valores["TITULAR"]), "titular")
    if not re.match(r"^[0-9]+\.[0-9]+\.[0-9]+$", str(valores["CLAUDE_VERSAO"])):
        raise EntradaInvalida(f"versão do Claude Code inválida: {valores['CLAUDE_VERSAO']!r}")
    modelo = modelo if modelo is not None else MODELO_LANCADOR.read_text(encoding="utf-8")
    for m in MARCADOR.finditer(modelo):
        if modelo[m.start() - 1:m.start()] != "'" or modelo[m.end():m.end() + 1] != "'":
            raise EntradaInvalida(f"marcador fora de aspas simples no modelo do lançador: {m.group(0)}")
    texto = renderizar(modelo, {k: _aspas_bash(str(v)) for k, v in valores.items()})
    if "\r" in texto or not texto.startswith("#!/usr/bin/env bash\n"):
        raise EntradaInvalida("modelo do lançador sem a primeira linha do bash ou com CR")
    return texto


def ler_bytes(caminho) -> bytes:
    caminho = Path(caminho)
    if not caminho.is_file():
        raise EntradaInvalida(f"arquivo ausente: {caminho}")
    return caminho.read_bytes()


def sha256_arquivo(caminho) -> str:
    return hashlib.sha256(ler_bytes(caminho)).hexdigest()


def valores_conferidos(raiz, projeto: str, titular: str) -> dict:
    """SHA-256 do perfil, dos hooks e do settings.local.json da raiz, cada um calculado sobre os mesmos bytes que
    passaram na conferência: o lançador só fixa o que confere [auditoria Codex Security da 1.7.6, #5]."""
    raiz, claude = Path(raiz), Path(raiz) / ".claude"
    identificador(projeto, "projeto")
    existentes = projetos_da_raiz(raiz)
    if projeto not in existentes:
        raise EntradaInvalida(f"projeto {projeto} ausente em {raiz / 'projects'}")
    perfil = ler_bytes(claude / "settings.wsl.json")
    problemas = conferir_perfil_wsl(json.loads(perfil.decode("utf-8")), caminho_wsl(str(raiz)), projeto,
                                    [p for p in existentes if p != projeto])
    if problemas:
        raise EntradaInvalida("o perfil do WSL (.claude/settings.wsl.json) não confere: " + "; ".join(problemas))
    ganchos = {}
    for nome in HOOKS:
        atual = ler_bytes(claude / "hooks" / nome)
        if atual != ler_bytes(MODELO_HOOKS / nome):
            raise EntradaInvalida(f"o hook {nome} da raiz difere do da skill ({MODELO_HOOKS / nome}): rode de novo o "
                                  f"preparar-maquina.ps1 no Windows")
        ganchos[nome] = hashlib.sha256(atual).hexdigest()
    local = ler_bytes(claude / "settings.local.json")
    problemas = conferir_identidade(json.loads(local.decode("utf-8-sig")), titular, projeto)
    if problemas:
        raise EntradaInvalida("o settings.local.json não confere: " + "; ".join(problemas))
    return {"TITULAR": titular, "PERFIL_SHA256": hashlib.sha256(perfil).hexdigest(),
            "HOOK_CAMINHO_SHA256": ganchos["guarda_caminho.py"],
            "HOOK_IDENTIDADE_SHA256": ganchos["guarda_identidade.py"],
            "LOCAL_SHA256": hashlib.sha256(local).hexdigest()}


def gravar(destino, texto: str) -> None:
    """Grava inteiro ou nada: arquivo temporário ao lado e troca no fim."""
    destino = Path(destino)
    temporario = destino.with_name("." + destino.name + ".tmp")
    temporario.write_text(texto, encoding="utf-8", newline="\n")
    temporario.replace(destino)


def _entregar(texto: str, saida) -> None:
    if saida:
        gravar(saida, texto)
    else:
        sys.stdout.write(texto)


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("perfil-windows")
    w.add_argument("--raiz", required=True)
    w.add_argument("--python", required=True)
    w.add_argument("--negar-skill", action="append", default=[], help="skill aninhada em pasta de dados")
    w.add_argument("--saida")
    s = sub.add_parser("perfil-wsl")
    s.add_argument("--raiz", required=True)
    s.add_argument("--projeto", required=True)
    s.add_argument("--perfil-windows", required=True)
    s.add_argument("--backups", action="append", default=[])
    s.add_argument("--somente-leitura", action="append", default=[])
    s.add_argument("--ancora-base", default=ANCORA_BASE_WSL)
    s.add_argument("--montagem", default=MONTAGEM)
    s.add_argument("--negar-skill", action="append", default=[], help="skill aninhada em pasta de dados")
    s.add_argument("--saida")
    i = sub.add_parser("identidade")
    i.add_argument("--titular", required=True)
    i.add_argument("--projeto", help="projeto autenticado das sessões (FUNDACAO_PROJECT)")
    i.add_argument("--atual", help="settings.local.json existente: acrescenta só a identidade")
    i.add_argument("--estrito", action="store_true", help="só a identidade e o projeto (sessão de dados reais)")
    i.add_argument("--saida")
    c = sub.add_parser("wsl-conf")
    c.add_argument("--arquivo", required=True)
    c.add_argument("--saida")
    k = sub.add_parser("conferir-perfil-wsl")
    k.add_argument("--perfil", required=True)
    k.add_argument("--raiz", required=True)
    k.add_argument("--projeto", required=True)
    d = sub.add_parser("conferir-identidade")
    for nome in ("--arquivo", "--titular", "--projeto"):
        d.add_argument(nome, required=True)
    lanc = sub.add_parser("lancador")
    for nome in ("--raiz", "--projeto", "--titular", "--claude", "--claude-versao", "--claude-sha256", "--origem-hash",
                 "--skill-md", "--saida"):
        lanc.add_argument(nome, required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "perfil-windows":
            _entregar(texto_json(perfil_windows(raiz=a.raiz, python=a.python, negar=a.negar_skill)), a.saida)
        elif a.cmd == "perfil-wsl":
            existentes = projetos_da_raiz(a.raiz)
            if a.projeto not in existentes:
                raise EntradaInvalida(f"projeto {a.projeto} ausente em {Path(a.raiz) / 'projects'}")
            perfil = perfil_wsl(raiz=a.raiz, projeto=a.projeto, perfil_windows=a.perfil_windows,
                                outros_projetos=[p for p in existentes if p != a.projeto], backups=a.backups,
                                somente_leitura=a.somente_leitura, ancora_base=a.ancora_base, montagem=a.montagem,
                                negar=a.negar_skill)
            _entregar(texto_json(perfil), a.saida)
        elif a.cmd == "identidade":
            atual = json.loads(Path(a.atual).read_text(encoding="utf-8-sig")) if a.atual else None
            _entregar(texto_json(identidade(a.titular, atual, a.projeto, estrito=a.estrito)), a.saida)
        elif a.cmd == "wsl-conf":
            arquivo = Path(a.arquivo)
            atual = arquivo.read_text(encoding="utf-8") if arquivo.is_file() else ""
            novo, mudou = ajustar_wsl_conf(atual)
            if a.saida:
                gravar(a.saida, novo)
            print(json.dumps({"arquivo": str(arquivo), "existia": arquivo.is_file(), "mudou": mudou, "texto": novo},
                             ensure_ascii=False))
        elif a.cmd == "conferir-perfil-wsl":
            perfil = json.loads(Path(a.perfil).read_text(encoding="utf-8"))
            existentes = projetos_da_raiz(a.raiz)
            problemas = ([] if a.projeto in existentes
                         else [f"projeto {a.projeto} ausente em {Path(a.raiz) / 'projects'}"])
            raiz_wsl = caminho_wsl(a.raiz)
            problemas += conferir_perfil_wsl(perfil, raiz_wsl, identificador(a.projeto, "projeto"),
                                             [p for p in existentes if p != a.projeto])
            try:  # as vagas vão no relatório: backups, pastas só de leitura e o resto que o Windows pôs no perfil
                vagas = parametros_do_perfil_wsl(perfil, raiz_wsl)
            except EntradaInvalida:
                vagas = None
            print(json.dumps({"perfil": a.perfil, "ok": not problemas, "problemas": problemas, "vagas": vagas},
                             ensure_ascii=False))
            return 0 if not problemas else 1
        elif a.cmd == "conferir-identidade":
            dados = ler_bytes(a.arquivo)
            problemas = conferir_identidade(json.loads(dados.decode("utf-8-sig")), a.titular, a.projeto)
            print(json.dumps({"arquivo": a.arquivo, "ok": not problemas, "titular": a.titular, "problemas": problemas,
                              "sha256": hashlib.sha256(dados).hexdigest()}, ensure_ascii=False))
            return 0 if not problemas else 1
        elif a.cmd == "lancador":
            valores = {"RAIZ": caminho_wsl(a.raiz), "PROJETO": a.projeto, "CLAUDE_BIN": caminho_wsl(a.claude),
                       "CLAUDE_VERSAO": a.claude_versao, "CLAUDE_SHA256": a.claude_sha256,
                       "CLAUDE_ORIGEM_HASH": a.origem_hash, "SKILL_MD": caminho_wsl(a.skill_md),
                       **valores_conferidos(a.raiz, a.projeto, a.titular)}
            texto = lancador(valores)
            if a.saida == "-":  # só o texto, para comparar com o lançador atual sem gravar (simulação)
                sys.stdout.write(texto)
                return 0
            gravar(a.saida, texto)
            print(json.dumps({"lancador": a.saida, "sha256": sha256_arquivo(a.saida),
                              **{k.lower(): v for k, v in valores.items() if k.endswith("SHA256")}}, ensure_ascii=False))
    except Conflito as exc:
        print(json.dumps({"conflito": str(exc)}, ensure_ascii=False))
        return 1
    except (EntradaInvalida, OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(json.dumps({"erro": str(exc)}, ensure_ascii=False))
        return 2
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # mesmo texto da --saida, também no Windows
    raise SystemExit(main())
