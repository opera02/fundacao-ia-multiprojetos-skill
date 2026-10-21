#!/usr/bin/env python3
r"""Preparo do host da fundação para dados reais: perfis do Claude Code gerados pelos modelos da skill, o
`/etc/wsl.conf` com um só bloco [interop] desligado e o lançador da sessão de dados reais no WSL2.

Na implantação de 2026-10-20 o perfil do WSL levou três versões (v1: `state/` virou tmpfs vazio no sandbox, porque
`Read(./state/**)` também vira `denyRead`; v2: só leitura; v3: leitura e escrita) e hooks e perfis foram copiados à
mão. Aqui os perfis saem dos modelos `windows/settings.json` e `wsl/settings.wsl.json` com os caminhos da máquina.
Chamado por `windows/preparar-maquina.ps1` e `wsl/preparar-wsl.sh`. Só grava com `--saida`; de `projects/` lê só os
nomes do primeiro nível (para negar, no sandbox, a escrita nos outros projetos). Biblioteca padrão.

  python preparo_host.py perfil-windows --raiz <raiz> --python <python.exe> [--saida <arquivo>]
  python preparo_host.py perfil-wsl --raiz <raiz> --projeto <id> --perfil-windows <C:\Users\nome>
         [--backups <pasta>]... [--somente-leitura <pasta>]... [--ancora-base <pasta>] [--saida <arquivo>]
  python preparo_host.py identidade --titular <id> [--atual <settings.local.json>] [--saida <arquivo>]
  python preparo_host.py wsl-conf --arquivo <wsl.conf> [--saida <arquivo>]     (JSON com "mudou" e "texto")
  python preparo_host.py conferir-perfil-wsl --perfil <settings.wsl.json> --raiz <raiz>
  python preparo_host.py lancador --raiz <raiz> --projeto <id> --claude <binário> --claude-versao <v>
         --claude-sha256 <hash> --origem-hash <texto> --skill-md <SKILL.md> --saida <arquivo | ->
Códigos: 0 ok · 1 conferência com problemas ou conflito (nada gravado) · 2 uso incorreto ou entrada
inválida (nada gravado).
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import ntpath
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
MODELO_WINDOWS = AQUI / "windows" / "settings.json"
MODELO_WSL = AQUI / "wsl" / "settings.wsl.json"
MODELO_LANCADOR = AQUI / "wsl" / "abrir-sessao.sh"
ANCORA_BASE_WSL = "/mnt/c/ProgramData/FundacaoIA"  # a pasta da âncora do Windows (allowed_signers), vista do WSL
MONTAGEM = "/mnt/"  # [automount] root padrão do WSL
IDENTIFICADOR = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MARCADOR = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
BARRA_INVERTIDA = chr(92)
CHAVE_IDENTIDADE = "FUNDACAO_" + "PRINCIPAL"  # a variável que o lançador entrega às sessões
CHAVES_DO_LANCADOR = ("RAIZ", "PROJETO", "CLAUDE_BIN", "CLAUDE_VERSAO", "CLAUDE_SHA256", "CLAUDE_ORIGEM_HASH",
                      "PERFIL_SHA256", "HOOK_CAMINHO_SHA256", "HOOK_IDENTIDADE_SHA256", "SKILL_MD")


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


def perfil_windows(*, raiz: str, python: str, modelo: dict | None = None) -> dict:
    """`.claude/settings.json` da raiz (sessões do Windows): negações, MCP do aplicativo e os dois hooks."""
    if not ntpath.isabs(str(raiz)) or not ntpath.isabs(str(python)):
        raise EntradaInvalida("raiz e python precisam ser caminhos absolutos do Windows")
    raiz, python = ntpath.normpath(str(raiz)), ntpath.normpath(str(python))  # barras do Windows nos caminhos
    pasta = ntpath.join(raiz, ".claude", "hooks")
    valores = {"PYTHON": python, "HOOK_CAMINHO": ntpath.join(pasta, "guarda_caminho.py"),
               "HOOK_IDENTIDADE": ntpath.join(pasta, "guarda_identidade.py")}
    return renderizar(modelo or ler_modelo(MODELO_WINDOWS), valores)


def perfil_wsl(*, raiz: str, projeto: str, perfil_windows: str, outros_projetos, backups=(), somente_leitura=(),
               ancora_base: str = ANCORA_BASE_WSL, montagem: str = MONTAGEM, modelo: dict | None = None) -> dict:
    """`.claude/settings.wsl.json` (sessão de dados reais no WSL2, sandbox estrito): `state/` legível e gravável
    pelos comandos do sandbox e negado à ferramenta Read; escrita negada nos outros projetos, na área do titular
    (`.claude`), na pasta da âncora e nas pastas só de leitura."""
    identificador(projeto, "projeto")
    outros = sorted({identificador(p, "projeto") for p in outros_projetos})
    if projeto in outros:
        raise EntradaInvalida(f"o projeto da sessão ({projeto}) não pode estar entre os projetos negados")
    raiz_wsl = caminho_wsl(raiz, montagem)
    valores = {"RAIZ": raiz_wsl, "PERFIL_WINDOWS": caminho_wsl(perfil_windows, montagem),
               "ANCORA_BASE": caminho_wsl(ancora_base, montagem),
               "HOOK_CAMINHO": raiz_wsl + "/.claude/hooks/guarda_caminho.py",
               "HOOK_IDENTIDADE": raiz_wsl + "/.claude/hooks/guarda_identidade.py"}
    listas = {"OUTROS_PROJETOS": outros,
              "BACKUPS": [caminho_wsl(b, montagem) for b in backups],
              "SOMENTE_LEITURA": [caminho_wsl(s, montagem) for s in somente_leitura]}
    perfil = renderizar(modelo or ler_modelo(MODELO_WSL), valores, listas)
    problemas = conferir_perfil_wsl(perfil, raiz_wsl)
    if problemas:
        raise EntradaInvalida("o modelo do perfil do WSL não garante: " + "; ".join(problemas))
    return perfil


def projetos_da_raiz(raiz) -> list[str]:
    """Nomes das pastas no primeiro nível de `projects/` (sem entrar nelas e sem pastas ocultas)."""
    pasta = Path(raiz) / "projects"
    if not pasta.is_dir():
        return []
    return sorted(p.name for p in pasta.iterdir() if p.is_dir() and not p.name.startswith("."))


def identidade(titular: str, atual: dict | None = None) -> dict:
    """`.claude/settings.local.json`: a identidade das sessões vem do lançador (regime de dados reais). Com o
    arquivo atual, acrescenta só a identidade e mantém o resto; outra identidade já gravada é `Conflito`."""
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
    return novo


def conferir_perfil_wsl(perfil: dict, raiz_wsl: str) -> list[str]:
    """O que o caso real provou (sandbox estrito com `state/` utilizável e a área do titular protegida)."""
    problemas = []
    sandbox = perfil.get("sandbox") or {}
    fs = sandbox.get("filesystem") or {}
    state = raiz_wsl.rstrip("/") + "/state"
    if sandbox.get("enabled") is not True or sandbox.get("failIfUnavailable") is not True:
        problemas.append("sandbox desligado ou sem falha obrigatória (failIfUnavailable)")
    if sandbox.get("allowUnsandboxedCommands") is not False:
        problemas.append("comandos fora do sandbox permitidos (allowUnsandboxedCommands)")
    if state not in (fs.get("allowRead") or []):
        problemas.append("state/ sem leitura no sandbox (v1: tmpfs vazio, com banco falso)")
    if state not in (fs.get("allowWrite") or []):
        problemas.append("state/ sem escrita no sandbox (v2: só leitura)")
    if raiz_wsl.rstrip("/") + "/.claude" not in (fs.get("denyWrite") or []):
        problemas.append(".claude da raiz gravável pelo sandbox")
    if "Read(./state/**)" not in ((perfil.get("permissions") or {}).get("deny") or []):
        problemas.append("ferramenta Read com acesso a state/")
    comandos = [h for g in ((perfil.get("hooks") or {}).get("PreToolUse") or []) for h in g.get("hooks", [])]
    esperados = {raiz_wsl.rstrip("/") + "/.claude/hooks/" + n for n in ("guarda_caminho.py", "guarda_identidade.py")}
    if not esperados <= {a for h in comandos for a in h.get("args", [])}:
        problemas.append("hooks guarda_caminho e guarda_identidade da raiz ausentes")
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
    for k in ("CLAUDE_SHA256", "PERFIL_SHA256", "HOOK_CAMINHO_SHA256", "HOOK_IDENTIDADE_SHA256"):
        if not SHA256.match(str(valores[k])):
            raise EntradaInvalida(f"{k} não é um SHA-256 em hexadecimal minúsculo: {valores[k]!r}")
    identificador(str(valores["PROJETO"]), "projeto")
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


def sha256_arquivo(caminho) -> str:
    caminho = Path(caminho)
    if not caminho.is_file():
        raise EntradaInvalida(f"arquivo ausente: {caminho}")
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


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
    w.add_argument("--saida")
    s = sub.add_parser("perfil-wsl")
    s.add_argument("--raiz", required=True)
    s.add_argument("--projeto", required=True)
    s.add_argument("--perfil-windows", required=True)
    s.add_argument("--backups", action="append", default=[])
    s.add_argument("--somente-leitura", action="append", default=[])
    s.add_argument("--ancora-base", default=ANCORA_BASE_WSL)
    s.add_argument("--montagem", default=MONTAGEM)
    s.add_argument("--saida")
    i = sub.add_parser("identidade")
    i.add_argument("--titular", required=True)
    i.add_argument("--atual", help="settings.local.json existente: acrescenta só a identidade")
    i.add_argument("--saida")
    c = sub.add_parser("wsl-conf")
    c.add_argument("--arquivo", required=True)
    c.add_argument("--saida")
    k = sub.add_parser("conferir-perfil-wsl")
    k.add_argument("--perfil", required=True)
    k.add_argument("--raiz", required=True)
    lanc = sub.add_parser("lancador")
    for nome in ("--raiz", "--projeto", "--claude", "--claude-versao", "--claude-sha256", "--origem-hash",
                 "--skill-md", "--saida"):
        lanc.add_argument(nome, required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "perfil-windows":
            _entregar(texto_json(perfil_windows(raiz=a.raiz, python=a.python)), a.saida)
        elif a.cmd == "perfil-wsl":
            existentes = projetos_da_raiz(a.raiz)
            if a.projeto not in existentes:
                raise EntradaInvalida(f"projeto {a.projeto} ausente em {Path(a.raiz) / 'projects'}")
            perfil = perfil_wsl(raiz=a.raiz, projeto=a.projeto, perfil_windows=a.perfil_windows,
                                outros_projetos=[p for p in existentes if p != a.projeto], backups=a.backups,
                                somente_leitura=a.somente_leitura, ancora_base=a.ancora_base, montagem=a.montagem)
            _entregar(texto_json(perfil), a.saida)
        elif a.cmd == "identidade":
            atual = json.loads(Path(a.atual).read_text(encoding="utf-8-sig")) if a.atual else None
            _entregar(texto_json(identidade(a.titular, atual)), a.saida)
        elif a.cmd == "wsl-conf":
            arquivo = Path(a.arquivo)
            atual = arquivo.read_text(encoding="utf-8") if arquivo.is_file() else ""
            novo, mudou = ajustar_wsl_conf(atual)
            if a.saida:
                gravar(a.saida, novo)
            print(json.dumps({"arquivo": str(arquivo), "existia": arquivo.is_file(), "mudou": mudou, "texto": novo},
                             ensure_ascii=False))
        elif a.cmd == "conferir-perfil-wsl":
            problemas = conferir_perfil_wsl(json.loads(Path(a.perfil).read_text(encoding="utf-8")),
                                            caminho_wsl(a.raiz))
            print(json.dumps({"perfil": a.perfil, "ok": not problemas, "problemas": problemas}, ensure_ascii=False))
            return 0 if not problemas else 1
        elif a.cmd == "lancador":
            raiz = Path(a.raiz)
            valores = {"RAIZ": caminho_wsl(a.raiz), "PROJETO": a.projeto, "CLAUDE_BIN": caminho_wsl(a.claude),
                       "CLAUDE_VERSAO": a.claude_versao, "CLAUDE_SHA256": a.claude_sha256,
                       "CLAUDE_ORIGEM_HASH": a.origem_hash,
                       "PERFIL_SHA256": sha256_arquivo(raiz / ".claude" / "settings.wsl.json"),
                       "HOOK_CAMINHO_SHA256": sha256_arquivo(raiz / ".claude" / "hooks" / "guarda_caminho.py"),
                       "HOOK_IDENTIDADE_SHA256": sha256_arquivo(raiz / ".claude" / "hooks" / "guarda_identidade.py"),
                       "SKILL_MD": caminho_wsl(a.skill_md)}
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
    except (EntradaInvalida, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"erro": str(exc)}, ensure_ascii=False))
        return 2
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # mesmo texto da --saida, também no Windows
    raise SystemExit(main())
