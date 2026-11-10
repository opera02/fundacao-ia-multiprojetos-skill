"""Skills com scripts no preparo do Ubuntu (1.7.11, lote S2; desenho de skills e agentes, §3.5 e §4.4).

O que o `preparo_host.py instalar-projeto` (com sudo) faz por uma skill da ficha que traz `skills_com_scripts`, chamando
este módulo (ele só roda ligado ao preparo, por `configurar`):
- confere o nome: skill ou agente da ficha cujo nome já está negado no registro (de qualquer projeto) é recusado, porque
  a negação do nome simples vale também para `<plugin>:<nome>` e não tem exceção (prova N-SK-7);
- com `dependencias`, confere a pasta das rodas (wheels) que o titular baixou contra o `requirements.lock` da skill (cada
  `.whl` com o SHA-256 que o lock lista; roda que falta ou que sobra recusa), copia as rodas para a área root pela cópia
  conferida e monta a venv SEM rede: `pip install --no-index --no-deps --only-binary=:all: --require-hashes` a partir de
  `/` e com o ambiente mínimo, em `<skills>/<projeto>/<plugin>/<lock_sha[:12]>/{rodas,venv}`;
- grava no `hashes.json` (chave `skills`) o interpretador real (`/usr/bin/python3.<m>`, caminho e SHA-256) e a árvore da
  venv (um SHA-256 sobre arquivo e ligação relativa); o executor (lote S3) reconfere os dois a cada execução. É confiança
  no primeiro uso, feito pelo titular: o pip não gera saída idêntica byte a byte.
Não prende: o código das rodas (o hash prova que são as baixadas, não que são seguras; um `.pth` roda a cada partida do
interpretador) e o pip como root (endurecer com um usuário sem privilégio é a medida M-S7). Nada aqui baixa algo: as rodas
vêm da pasta do projeto (`outputs/rodas-<skill>-<data>/`). Só biblioteca padrão.
"""

from __future__ import annotations

import hashlib
import importlib
import os
import posixpath
import re
import shutil
import stat
import subprocess
import time
from pathlib import Path

H = None  # o preparo_host (classe de erro, pastas de dono root e leitura conferida): ligado por `configurar`
SKILLS_BASE = "/usr/local/lib/fundacao-ia/skills"
PYTHON = "/usr/bin/python3"
TEMPO_PIP = 1800
TETO_ARQUIVOS_VENV, TETO_RODAS, TETO_RODAS_BYTES, TETO_LOCK, TETO_SKILL_MD = 60000, 300, 2 << 30, 64 * 1024, 1 << 20
AMBIENTE = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
            "PIP_CONFIG_FILE": "/dev/null", "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PYTHONDONTWRITEBYTECODE": "1"}
RODA = re.compile(r"^(?P<dist>[A-Za-z0-9][A-Za-z0-9._]*)-(?P<ver>[A-Za-z0-9._+!]+)(?:-[0-9][A-Za-z0-9_.]*)?-"
                  r"[A-Za-z0-9_.]+-[A-Za-z0-9_.]+-[A-Za-z0-9_.]+\.whl$")
PACOTE = re.compile(r"(?m)^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[a-z0-9,_-]+\])?==([A-Za-z0-9.+!_-]+)"
                    r"((?: \\\n +--hash=sha256:[0-9a-f]{64})+)$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
CAMPOS_DO_SCRIPT, CAMPOS_DAS_DEPENDENCIAS = {"nome", "caminho", "sha256", "modo"}, {"lock", "lock_sha256", "rodas",
                                                                                     "python", "pacotes"}


def erro(mensagem: str) -> Exception:
    return (H.EntradaInvalida if H is not None else ValueError)(mensagem)


def configurar(host) -> None:
    """Liga o módulo ao preparo_host (a classe de erro que o main dele trata e as gravações de dono root)."""
    global H
    H = host


def rodar(argv, *, cwd="/", env=None, tempo=TEMPO_PIP) -> tuple[int, str]:
    """(código, saída) de um programa, sem entrada (`stdin` fechado) e com prazo. Os testes de unidade trocam esta função."""
    try:
        p = subprocess.run(list(argv), cwd=cwd, env=env if env is not None else dict(AMBIENTE), stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=tempo, text=True, encoding="utf-8",
                           errors="replace")
    except subprocess.TimeoutExpired:  # o run já matou o filho; vira falha do passo, com o motivo
        return 124, f"prazo de {tempo} s esgotado"
    return p.returncode, p.stdout or ""


def _kit(skill, nome: str):
    """Módulo `core/<nome>` do kit DESTA cópia da skill (o mesmo pacote que o preparo já carregou para a ficha)."""
    base = H.modulos_do_kit(skill).plugins.__name__.rsplit(".", 1)[0]
    return importlib.import_module(base + "." + nome)


# ------------------------------------------------------------------ a ficha
def scripts_do_plugin(plugin: str, valor) -> list[dict]:
    """O `skills_com_scripts` de um `plugins[]` na forma que o preparo usa, ou EntradaInvalida. A regra da ficha é a do kit
    (já aplicada); aqui só os tipos, para o aberturas.json e a venv nunca levarem o que o executor não entende."""
    if valor is None or valor == []:
        return []
    ruim = erro(f"plugin {plugin}: skills_com_scripts fora da forma (lista de skill, skill_md_sha256, scripts e, se houver "
                "pacotes, dependencias)")
    if not isinstance(valor, list):
        raise ruim
    saida = []
    for s in valor:
        if (not isinstance(s, dict) or not {"skill", "skill_md_sha256", "scripts"} <= set(s)
                or set(s) - {"skill", "skill_md_sha256", "scripts", "dependencias"}
                or not isinstance(s["skill"], str) or not isinstance(s["scripts"], list) or not s["scripts"]
                or not isinstance(s["skill_md_sha256"], str) or not SHA256.match(s["skill_md_sha256"])):
            raise ruim
        for sc in s["scripts"]:
            if (not isinstance(sc, dict) or set(sc) != CAMPOS_DO_SCRIPT or not isinstance(sc["sha256"], str)
                    or not SHA256.match(sc["sha256"]) or not all(isinstance(sc[c], str) for c in CAMPOS_DO_SCRIPT)):
                raise ruim
        dep = s.get("dependencias")
        if dep is not None and (not isinstance(dep, dict) or set(dep) != CAMPOS_DAS_DEPENDENCIAS
                                or not all(isinstance(dep[c], str) for c in ("lock", "rodas", "python"))
                                or not isinstance(dep["lock_sha256"], str) or not SHA256.match(dep["lock_sha256"])
                                or isinstance(dep["pacotes"], bool) or not isinstance(dep["pacotes"], int)):
            raise ruim
        saida.append({k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v)
                      for k, v in s.items()})
    return saida


# ------------------------------------------------------------------ nome contra o registro (N-SK-7)
def _nome_do_cabecalho(dados: bytes, skill) -> str | None:
    cabecalho = _kit(skill, "aberturas_agentes").ler_cabecalho(dados) or {}
    valores = cabecalho.get("name") or []
    if len(valores) != 1 or "\n" in valores[0].strip():
        return None
    valor = re.sub(r"\s+#.*\Z", "", valores[0].strip())
    return (valor[1:-1] if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "'\"" else valor) or None


def conferir_nomes(projeto: str, plugin: str, manifesto, origem, agentes, registro, skill) -> None:
    """Recusa a skill (o nome da pasta ou o `name` do `SKILL.md`) e o agente da ficha cujo nome já está negado no registro,
    de qualquer projeto: a negação não tem exceção na ficha, e a saída é renomear no candidato."""
    itens = list(registro["projetos"].values())
    skills = {n.casefold() for i in itens for n in i.get("aninhadas_negadas", [])}
    negados = {n.casefold() for i in itens for n in i.get("agentes_negados", [])}
    achados = []
    for pasta in H._pastas_de_skill(manifesto):
        nomes = {pasta}
        try:
            dados = H._ler_bytes_seguro(Path(origem) / "skills" / pasta / "SKILL.md", TETO_SKILL_MD, origem)
            nomes.add(_nome_do_cabecalho(dados, skill) or pasta)
        except (OSError, ValueError):
            pass  # o kit já leu e conferiu o arquivo; aqui só o nome, e a pasta basta
        achados += [f"renomeie a skill {n!r} no candidato (por exemplo, {projeto}-{n}): o nome está negado no registro e a "
                    "negação não tem exceção" for n in sorted(nomes) if n.casefold() in skills]
    achados += [f"renomeie o agente {a['nome']!r} no candidato e na ficha (por exemplo, {projeto}-{a['nome']}): o nome está "
                "negado no registro (Agent no perfil) e a negação não tem exceção"
                for a in agentes if a["nome"].casefold() in negados]
    if achados:
        raise erro(f"plugin {plugin}: " + "; ".join(achados[:4]))


# ------------------------------------------------------------------ o lock e as rodas (N-HASH-3)
def pacotes_do_lock(dados: bytes, skill) -> dict:
    """{nome normalizado: {"versao", "hashes"}} do requirements.lock, já na forma do kit (`ler_lock`)."""
    motivos, nomes = _kit(skill, "aberturas_scripts").ler_lock(dados)
    if motivos:
        raise erro("requirements.lock fora da forma: " + "; ".join(motivos[:3]))
    texto, pacotes = dados.decode("ascii").replace("\r\n", "\n"), {}
    for m in PACOTE.finditer(texto):
        pacotes[re.sub(r"[-_.]+", "-", m.group(1)).lower()] = {"versao": m.group(2),
                                                              "hashes": set(re.findall(r"sha256:([0-9a-f]{64})", m.group(3)))}
    if sorted(pacotes) != sorted(nomes):
        raise erro("requirements.lock: a leitura dos pacotes difere da do kit")
    return pacotes


def listar_rodas(pasta) -> list[dict]:
    """Os `.whl` da pasta, [{nome, sha256, bytes}] em ordem de nome, lidos sem seguir ligação. Só arquivo comum com nome de
    roda: o resto (pasta, ligação, outro tipo de arquivo) recusa."""
    copia, pasta = H._carregar_script("copia_segura"), Path(pasta)
    try:
        entradas = sorted(os.scandir(pasta), key=lambda e: e.name)
    except OSError as exc:
        raise erro(f"pasta das rodas ilegível ({exc.strerror or exc}): {pasta}") from None
    if not entradas or len(entradas) > TETO_RODAS:
        raise erro(f"a pasta das rodas tem {len(entradas)} itens (de 1 a {TETO_RODAS}): {pasta}")
    saida = []
    for e in entradas:
        st = e.stat(follow_symlinks=False)
        if copia.e_ligacao(st) or not stat.S_ISREG(st.st_mode) or not RODA.match(e.name):
            raise erro(f"a pasta das rodas tem {e.name!r}: só arquivo .whl comum com nome de roda, sem ligação nem pasta")
        try:
            saida.append({"nome": e.name, **copia.hash_conferido(e.path, dentro_de=pasta)})
        except OSError as exc:
            raise erro(f"roda {e.name} recusada: {exc}") from None
    if sum(r["bytes"] for r in saida) > TETO_RODAS_BYTES:
        raise erro(f"as rodas passam de {TETO_RODAS_BYTES >> 20} MiB")
    return saida


def conferir_rodas(pacotes: dict, rodas: list[dict]) -> None:
    """Cada roda é de um pacote do lock, na versão dele e com um dos SHA-256 que ele lista; cada pacote tem a sua. Roda
    que falta, que sobra ou que mudou depois da assinatura: EntradaInvalida (e o pip nem roda)."""
    problemas, cobertos = [], set()
    for r in rodas:
        m = RODA.match(r["nome"])
        chave = re.sub(r"[-_.]+", "-", m["dist"]).lower()
        p = pacotes.get(chave)
        if p is None:
            problemas.append(f"sobra a roda {r['nome']}: {chave} não está no lock")
        elif m["ver"].replace("_", "-").lower() != p["versao"].lower():
            problemas.append(f"sobra a roda {r['nome']}: o lock pede {chave}=={p['versao']}")
        elif r["sha256"] not in p["hashes"]:
            problemas.append(f"a roda {r['nome']} (SHA-256 {r['sha256'][:12]}...) difere das que o lock lista: não é a que o "
                             "titular travou (trocada depois da assinatura?)")
        else:
            cobertos.add(chave)
    problemas += [f"falta a roda de {n}=={p['versao']}" for n, p in sorted(pacotes.items()) if n not in cobertos]
    if problemas:
        mais = f"; e mais {len(problemas) - 5}" if len(problemas) > 5 else ""
        raise erro("rodas fora do lock (" + "; ".join(problemas[:5]) + mais + "): nada foi copiado e o pip não rodou")


# ------------------------------------------------------------------ o interpretador e a árvore da venv
def interpretador() -> dict:
    """O Python real do preparo (a ligação /usr/bin/python3 resolvida): caminho, SHA-256 e versão `3.<m>`."""
    real = os.path.realpath(PYTHON)
    try:
        sha = H._carregar_script("copia_segura").hash_conferido(real)["sha256"]
    except OSError as exc:
        raise erro(f"o interpretador {PYTHON} ({real}) não foi lido: {exc}") from None
    m = re.fullmatch(r"python(3\.[0-9]{1,2})", os.path.basename(real))
    if m:
        versao = m.group(1)
    else:
        codigo, saida = rodar([real, "-I", "-c", "import sys; print('%d.%d' % sys.version_info[:2])"], tempo=30)
        versao = saida.strip()
        if codigo != 0 or not re.fullmatch(r"3\.[0-9]{1,2}", versao):
            raise erro(f"a versão do Python {real} não foi lida")
    return {"caminho": real, "sha256": sha, "versao": versao}


def ligacao_da_venv_sai(rel: str, alvo: str) -> bool:
    r"""Verdadeiro (recusa) quando a ligação `rel -> alvo` da venv pode sair dela. Pura: lê só o texto, sem disco, e vale
    igual em qualquer sistema. A venv é do Ubuntu (POSIX): o alvo se lê como POSIX, sem trocar a barra invertida. No Windows
    o `os.path.normpath` devolvia "..\fora", que escapava do teste "../" (CI pública da 1.7.11); e trocar `\` por `/` antes de
    normalizar deixava passar, no Linux, `a\b/../../x` (F12 da revisão final): ali `a\b` é UM nome de pasta, não duas.
    Por isso o alvo com `\` ou `:` (unidade, UNC, `\?\`) é recusado direto. A conferência é lexical e não vê uma ligação de
    pasta no meio do caminho (o caminhamento não segue pasta ligada): só `..` no começo sobe por pastas reais, e `..` depois
    de um segmento normal é recusado."""
    if not alvo or "\\" in alvo or ":" in alvo or posixpath.isabs(alvo) or os.path.isabs(alvo):
        return True
    normal = False
    for segmento in alvo.split("/"):
        if segmento == "..":
            if normal:
                return True
        elif segmento not in ("", "."):
            normal = True
    dentro = posixpath.normpath(posixpath.join(posixpath.dirname(rel), alvo))
    return dentro == ".." or dentro.startswith("../") or posixpath.isabs(dentro)


def arvore_da_venv(pasta) -> dict:
    """{rel: {"sha256", "bytes"} | {"ligacao": alvo}} dos arquivos e das ligações sob a venv. A venv tem ligações (lib64,
    python3), então não serve o `manifesto_de_arvore`: aqui só vale ligação relativa que fica dentro dela; outro tipo de
    arquivo, vínculo físico ou mais de TETO_ARQUIVOS_VENV: EntradaInvalida."""
    copia, base = H._carregar_script("copia_segura"), Path(os.path.abspath(pasta))
    saida, pilha = {}, [base]
    while pilha:
        atual = pilha.pop()
        for nome in sorted(os.listdir(atual)):
            caminho = atual / nome
            rel, st = caminho.relative_to(base).as_posix(), os.lstat(caminho)
            if stat.S_ISLNK(st.st_mode):
                alvo = os.readlink(caminho)
                if ligacao_da_venv_sai(rel, alvo):
                    raise erro(f"ligação da venv que sai dela: {rel} -> {alvo}")
                saida[rel] = {"ligacao": alvo}
            elif stat.S_ISDIR(st.st_mode) and not copia.e_ligacao(st):
                pilha.append(caminho)
            elif stat.S_ISREG(st.st_mode) and not copia.e_ligacao(st):
                try:
                    saida[rel] = copia.hash_conferido(caminho, dentro_de=base)
                except OSError as exc:
                    raise erro(f"{rel}: {exc}") from None
            else:
                raise erro(f"tipo especial ou junção na venv: {rel}")
            if len(saida) > TETO_ARQUIVOS_VENV:
                raise erro(f"a venv tem mais de {TETO_ARQUIVOS_VENV} arquivos")
    return saida


def sha256_da_venv(arvore: dict) -> str:
    """SHA-256 das linhas `f<TAB>rel<TAB>bytes<TAB>sha` e `l<TAB>rel<TAB>alvo`, em ordem de caminho."""
    linhas = [f"l\t{rel}\t{m['ligacao']}\n" if "ligacao" in m else f"f\t{rel}\t{m['bytes']}\t{m['sha256']}\n"
              for rel, m in sorted(arvore.items())]
    return hashlib.sha256("".join(linhas).encode("utf-8")).hexdigest()


def _sem_pycache(venv) -> None:
    """O pip e o ensurepip compilam: a venv gravada não tem `__pycache__` (o interpretador roda com -B)."""
    for atual, pastas, _ in os.walk(venv):
        for nome in [p for p in pastas if p == "__pycache__"]:
            shutil.rmtree(Path(atual) / nome, ignore_errors=True)
            pastas.remove(nome)


# ------------------------------------------------------------------ o plano (sem gravar) e a montagem
def registro_anterior(area) -> dict:
    """O `skills` do hashes.json já instalado (para saber se a venv de agora é a mesma); ausente ou ilegível: nenhum."""
    try:
        dados = H._ler_json_seguro(Path(area) / "hashes.json", H.TETO_HASHES)
        return dados.get("skills") if isinstance(dados, dict) and isinstance(dados.get("skills"), dict) else {}
    except (OSError, ValueError):
        return {}


def planejar(projeto: str, plugin: str, itens: list, proj, origem, base, anterior: dict, skill) -> list[dict]:
    """O plano de cada skill com scripts do plugin, sem gravar nada: o interpretador e, com `dependencias`, o lock e as
    rodas conferidos (Python da ficha igual ao da máquina; lock com o SHA-256 da ficha; rodas iguais ao lock)."""
    inter, planos = interpretador(), []
    for s in itens:
        chave, dep, plano_dep = f"{plugin}:{s['skill']}", s.get("dependencias"), None
        if dep:
            if dep["python"] != inter["versao"]:
                raise erro(f"{chave}: a ficha pede o Python {dep['python']} e esta máquina tem o {inter['versao']} "
                           f"({inter['caminho']}): as rodas são do Python da ficha. Refaça o lock para o "
                           f"{inter['versao']} (plugin_candidato.py travar --skill {s['skill']} --rodas <pasta nova>) e "
                           "assine a ficha de novo")
            if H._carregar_script("gravacao_segura").com_ligacao(proj, dep["rodas"]):
                raise erro(f"{chave}: a pasta das rodas passa por ligação: {dep['rodas']}")
            dados = H._ler_bytes_seguro(Path(origem) / Path(*dep["lock"].split("/")), TETO_LOCK, origem)
            if hashlib.sha256(dados).hexdigest() != dep["lock_sha256"]:
                raise erro(f"{chave}: o requirements.lock mudou desde a ficha: prepare a ficha de novo")
            pasta_rodas = Path(proj) / Path(*dep["rodas"].split("/"))
            rodas = listar_rodas(pasta_rodas)
            conferir_rodas(pacotes_do_lock(dados, skill), rodas)
            raiz = Path(base) / projeto / plugin / dep["lock_sha256"][:12]
            plano_dep = {"lock": dep["lock"], "lock_sha256": dep["lock_sha256"], "pacotes": dep["pacotes"],
                         "rodas_origem": pasta_rodas, "rodas": rodas, "raiz": raiz, "venv": raiz / "venv"}
        planos.append({"chave": chave, "plugin": plugin, "skill": s["skill"], "scripts": s["scripts"],
                       "interpretador": inter, "dependencias": plano_dep, "anterior": _objeto(anterior.get(chave)),
                       "venv": None})
    return planos


def _objeto(valor) -> dict:
    return valor if isinstance(valor, dict) else {}


def _montar(plano: dict, dep: dict, area, raiz_dono: bool) -> dict:
    """Rodas para a área root pela cópia conferida (SHA-256 do plano) e a venv sem rede, a partir de `/`. Em qualquer
    falha, a pasta do lock some inteira (a venv leva caminhos absolutos: nada de montar ao lado e trocar de nome)."""
    copia, raiz, inicio = H._carregar_script("copia_segura"), dep["raiz"], time.monotonic()
    lock = Path(area) / "plugins" / plano["plugin"] / Path(*dep["lock"].split("/"))
    temp, antigo_umask = raiz / "tmp", os.umask(0o022)
    try:
        H._pasta_area(raiz, raiz_dono)
        for pasta in (raiz / "rodas", temp):
            H._pasta_area(pasta, raiz_dono)
        os.chmod(temp, 0o700)
        for r in dep["rodas"]:
            copia.copiar_conferindo(dep["rodas_origem"] / r["nome"], raiz / "rodas" / r["nome"], sha256_esperado=r["sha256"],
                                    modo=0o644, dentro_de=dep["rodas_origem"])
            H._dono(raiz / "rodas" / r["nome"], raiz_dono)
        if hashlib.sha256(H._ler_bytes_seguro(lock, TETO_LOCK, Path(area) / "plugins")).hexdigest() != dep["lock_sha256"]:
            raise erro("o requirements.lock da cópia root difere do da ficha: nada foi montado")
        ambiente = {**AMBIENTE, "TMPDIR": str(temp)}
        venv = dep["venv"]
        codigo, saida = rodar([PYTHON, "-I", "-B", "-m", "venv", "--copies", str(venv)], env=ambiente)
        if codigo == 0:
            codigo, saida = rodar([str(venv / "bin" / "python"), "-I", "-B", "-m", "pip", "install", "--no-index",
                                   "--no-deps", "--only-binary=:all:", "--require-hashes", "--no-compile",
                                   "--no-cache-dir", "--disable-pip-version-check", "--no-warn-script-location",
                                   "--find-links", str(raiz / "rodas"), "-r", str(lock)], env=ambiente)
        if codigo != 0:
            raise erro(f"{plano['chave']}: a venv não foi montada (código {codigo}); fim da saída do pip: "
                       + " ".join(saida.split())[-500:])
        shutil.rmtree(temp, ignore_errors=True)
        _sem_pycache(venv)
        arvore = arvore_da_venv(venv)
    except BaseException:
        shutil.rmtree(raiz, ignore_errors=True)
        raise
    finally:
        os.umask(antigo_umask)
    return {"caminho": venv.as_posix(), "sha256": sha256_da_venv(arvore), "arquivos": len(arvore),
            "bytes": sum(m.get("bytes", 0) for m in arvore.values()), "lock_sha256": dep["lock_sha256"],
            "duracao_s": round(time.monotonic() - inicio, 1)}


def construir(plano: dict, area, raiz_dono: bool, feitas: dict) -> list[dict]:
    """Grava a venv da skill (uma só por pasta de lock, mesmo que duas skills do plugin tenham o mesmo lock) e guarda o
    registro dela em `plano["venv"]`. 'igual': a venv instalada antes, do mesmo lock, ainda tem a árvore que o hashes.json
    registrou. Devolve as ações do relatório."""
    dep = plano["dependencias"]
    if not dep:
        return []
    raiz = dep["raiz"]
    if raiz in feitas:
        plano["venv"] = feitas[raiz]
        return []
    antes = _objeto(plano["anterior"].get("venv"))
    if os.path.lexists(raiz):
        try:
            igual = (antes.get("caminho") == dep["venv"].as_posix() and antes.get("lock_sha256") == dep["lock_sha256"]
                     and sha256_da_venv(arvore_da_venv(dep["venv"])) == antes.get("sha256"))
        except (OSError, ValueError):
            igual = False
        if igual:
            plano["venv"] = feitas[raiz] = {k: antes[k] for k in antes if k != "duracao_s"}
            return [{"item": f"venv:{plano['chave']}", "caminho": raiz.as_posix(), "acao": "igual"}]
        shutil.rmtree(raiz, ignore_errors=True)
    registro = _montar(plano, dep, area, raiz_dono)
    plano["venv"] = feitas[raiz] = {k: v for k, v in registro.items() if k != "duracao_s"}
    return [{"item": f"venv:{plano['chave']}", "caminho": raiz.as_posix(), "acao": "criar" if not antes else "refazer",
             "detalhe": f"{dep['pacotes']} pacotes, {registro['arquivos']} arquivos, {registro['bytes'] >> 20} MiB, "
                        f"{registro['duracao_s']} s, sem rede"}]


def registro_dos_hashes(planos: list[dict]) -> dict:
    """O `skills` do hashes.json: por `<plugin>:<skill>`, o interpretador e (com pacotes) a venv, o que o executor
    reconfere. Sem a venv montada ainda (plano, simulação), `venv` fica `null`."""
    return {p["chave"]: {"interpretador": p["interpretador"], "venv": p["venv"]} for p in planos}


def limpar_antigas(base, projeto: str, planos: list[dict]) -> list[dict]:
    """Depois do sucesso: as pastas de lock que nenhuma skill da ficha usa mais, e os plugins que saíram dela."""
    desejado: dict = {}
    for p in planos:
        if p["dependencias"]:
            desejado.setdefault(p["plugin"], set()).add(p["dependencias"]["raiz"].name)
    pasta, acoes = Path(base) / projeto, []
    try:
        plugins = sorted(os.listdir(pasta))
    except OSError:
        return acoes

    def tirar(caminho: Path) -> None:
        if caminho.is_symlink() or not caminho.is_dir():
            os.unlink(caminho)
        else:
            shutil.rmtree(caminho)
        acoes.append({"item": "venv-antiga", "caminho": caminho.as_posix(), "acao": "remover"})
    for nome in plugins:
        if nome not in desejado:
            tirar(pasta / nome)
            continue
        for filho in sorted(os.listdir(pasta / nome)):
            if filho not in desejado[nome]:
                tirar(pasta / nome / filho)
    return acoes


def resumo(planos: list[dict]) -> list[dict]:
    """O que o relatório mostra de cada skill com scripts (a venv, quando montada)."""
    saida = []
    for p in planos:
        dep = p["dependencias"] or {}
        saida.append({"skill": p["chave"], "scripts": [s["nome"] for s in p["scripts"]], "python": p["interpretador"]["versao"],
                      "pacotes": dep.get("pacotes"), "rodas": len(dep.get("rodas", [])),
                      "venv": dep["venv"].as_posix() if dep else None, "arvore_sha256": (p["venv"] or {}).get("sha256")})
    return saida


def avisos(planos: list[dict]) -> list[str]:
    """O aviso do titular sobre o código de terceiros (§4.3 do desenho): o hash prova o baixado, não o seguro."""
    return [f"skill {p['chave']}: {p['dependencias']['pacotes']} pacotes de terceiros instalados SEM rede em "
            f"{p['dependencias']['raiz'].as_posix()} (dono root; lock SHA-256 {p['dependencias']['lock_sha256'][:12]}...). O "
            "código deles roda junto com o script, e um arquivo .pth de uma roda roda a cada partida do interpretador; o "
            "hash prova que são os pacotes baixados por você, não que são seguros. O pip rodou como root (endurecer com um "
            "usuário sem privilégio é a medida M-S7, ainda não feita)" for p in planos if p["dependencias"]]


# ------------------------------------------------------------------ a reconferência (executor e conferir-abertura, lote S3)
def problemas_da_skill(chave: str, registro, venv_esperada=None) -> list[str]:
    """O interpretador e a venv de uma skill, reconferidos agora contra o que o preparo gravou no `skills` do hashes.json
    (`registro`: {"interpretador": {caminho, sha256}, "venv": {caminho, sha256, ...} | null}). Lista vazia: igual. É a
    mesma conta do preparo (`arvore_da_venv` e `sha256_da_venv`), usada pelo `conferir-abertura` e pelo executor antes de
    cada execução. `venv_esperada`: a pasta em que a venv desta skill tem de estar (o executor a calcula da ficha); sem
    ela, só vale caminho absoluto sem `..`."""
    comando = "rode de novo o preparar-wsl.sh (com sudo), que refaz o registro"
    r = _objeto(registro)
    inter, venv = _objeto(r.get("interpretador")), r.get("venv")
    caminho, sha = inter.get("caminho"), inter.get("sha256")
    if not (isinstance(caminho, str) and os.path.isabs(caminho) and isinstance(sha, str) and SHA256.match(sha)):
        return [f"skill {chave}: o hashes.json não tem o interpretador na forma esperada ({comando})"]
    problemas = []
    if os.path.realpath(PYTHON) != caminho:
        problemas.append(f"skill {chave}: {PYTHON} agora aponta para {os.path.realpath(PYTHON)}, e o preparo gravou "
                         f"{caminho} ({comando})")
    try:
        atual = H._carregar_script("copia_segura").hash_conferido(caminho)["sha256"]
    except OSError as exc:
        atual = f"(recusado: {exc.strerror or exc})"
    if atual != sha:
        problemas.append(f"skill {chave}: o interpretador {caminho} mudou desde o preparo (atualização do Python do "
                         f"sistema?); {comando}")
    if venv is None:
        return problemas
    pasta, soma = _objeto(venv).get("caminho"), _objeto(venv).get("sha256")
    if not (isinstance(pasta, str) and os.path.isabs(pasta) and ".." not in pasta.split("/") and isinstance(soma, str)
            and SHA256.match(soma)) or (venv_esperada is not None and pasta != Path(venv_esperada).as_posix()):
        return problemas + [f"skill {chave}: a venv do hashes.json está fora da forma ou fora da pasta esperada "
                            f"({str(pasta)[:120]}); {comando}"]
    try:
        atual = sha256_da_venv(arvore_da_venv(pasta))
    except (OSError, ValueError) as exc:  # EntradaInvalida é ValueError
        return problemas + [f"skill {chave}: a venv {pasta} não foi lida ({str(exc)[:150]}); {comando}"]
    if atual != soma:
        problemas.append(f"skill {chave}: a venv {pasta} mudou desde o preparo (um arquivo trocado, a mais ou a menos; "
                         f"esperado {soma[:12]}..., encontrado {atual[:12]}...); se foi você, {comando}; se não foi, não "
                         "rode o script")
    return problemas


def problemas_da_abertura(hashes) -> list[str]:
    """O `conferir-abertura`: cada skill com scripts do hashes.json (chave `skills`) tem o interpretador e a venv que o
    preparo gravou. Sem a chave, a ficha não tem skill com scripts e nada é conferido."""
    registro = _objeto(hashes).get("skills")
    if registro is None:
        return []
    if not isinstance(registro, dict):
        return ["skills com scripts: o hashes.json está fora da forma; rode de novo o preparar-wsl.sh (com sudo)"]
    return [p for chave, r in sorted(registro.items()) for p in problemas_da_skill(str(chave), r)]
