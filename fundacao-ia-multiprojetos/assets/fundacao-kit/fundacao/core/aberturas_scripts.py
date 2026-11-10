"""Skills com scripts de plugin pela ficha de aberturas (1.7.11, lote S1; desenho de skills e agentes, §3.1, §4.1 e §4.2).

Um script de skill (`skills/<skill>/scripts/<nome>.py`) e a lista de pacotes dela (`skills/<skill>/requirements.lock`) só
valem se o item `plugins[]` da ficha os lista em `skills_com_scripts[] {skill, skill_md_sha256, scripts[], dependencias}`:
a ficha prende o SHA-256 do `SKILL.md`, de cada script e do lock, o modo de rodar e, nas dependências, a pasta das rodas
(wheels), a versão do Python e a contagem de pacotes. O arquivo de código fora da lista, no lugar errado, de outra
linguagem ou com `#!` continua recusado ("1.7.11"): o plugin inteiro é recusado, e nenhuma assinatura derruba isso.

Regras fixas:
- o plugin com `skills_com_scripts` tem de se chamar `<projeto>-<nome>` (erro; os plugins só de Markdown seguem com o
  aviso); até 5 skills por plugin e 10 na ficha, cada skill uma vez só e com o `SKILL.md` presente;
- de 1 a 10 scripts por skill e até 20 na ficha: `nome` em `[a-z][a-z0-9-]{0,31}` (sem repetir na skill) e igual ao nome
  do arquivo sem `.py`, com `_` trocado por `-` (o que o titular vê é o que roda), `caminho`
  exatamente `skills/<skill>/scripts/<arquivo>.py` (arquivo em `[a-z][a-z0-9_]{0,31}`), `sha256` e `modo`
  (`sessao`; `caixa` só com o lote S4, e antes dele a ficha recusa com "1.7.11, lote S4");
- `dependencias`, opcional (sem ela o script roda só com a biblioteca padrão): `lock` exatamente
  `skills/<skill>/requirements.lock`, `lock_sha256`, `rodas` (pasta do projeto fora de data/ e do próprio candidato),
  `python` na lista medida (3.12) e `pacotes` igual à contagem do lock, que tem de estar na forma fixa de `ler_lock`
  (`nome==versão` e um ou mais `--hash=sha256:`; nenhuma opção, URL, caminho, marcador nem pacote repetido);
- o texto do `.py` é conferido por core/aberturas_markdown.py (`conferir_python`).
O que a conferência não faz: ler o que o script faz (é o que o titular lê na seção "Código que roda" do REVISAO.md) nem
provar que os pacotes do lock são seguros (o hash prova que são os baixados). A venv e o executor são dos lotes S2 e S3.

Este módulo é irmão do aberturas_regras (carregado na chamada, pelo pacote ou pelo arquivo vizinho): só biblioteca
padrão e nenhum outro módulo do kit. `validar`, `itens` e `descrever` seguem a forma dos irmãos; as outras funções são
chamadas pelo aberturas_plugins e pelo scripts/plugin_candidato.py.
"""

from __future__ import annotations

import re

TETO_SKILLS_PLUGIN, TETO_SKILLS_FICHA, TETO_SCRIPTS_SKILL, TETO_SCRIPTS_FICHA = 5, 10, 10, 20
TETO_LOCK, TETO_PACOTES = 64 * 1024, 300
CAMPOS_DA_SKILL = ("skill", "skill_md_sha256", "scripts")  # mais `dependencias`, opcional
CAMPOS_DO_SCRIPT = ("nome", "caminho", "sha256", "modo")
CAMPOS_DAS_DEPENDENCIAS = ("lock", "lock_sha256", "rodas", "python", "pacotes")
MODOS, MODOS_ABERTOS, PYTHONS = ("sessao", "caixa"), ("sessao",), ("3.12",)
NOME_DA_SKILL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?")
NOME_DO_SCRIPT = re.compile(r"[a-z][a-z0-9-]{0,31}")
ARQUIVO_DO_SCRIPT = re.compile(r"[a-z][a-z0-9_]{0,31}\.py")
SHA256 = re.compile(r"[0-9a-f]{64}")
# Um pacote do lock: uma linha lógica `nome[extras]==versão` com um ou mais `--hash=sha256:` em linhas de continuação.
_PACOTE = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[a-z0-9,_-]+\])?==[A-Za-z0-9.+!_-]+(?: \\\n +--hash=sha256:[0-9a-f]{64})+")


def _mostrar(valor) -> str:
    texto = ascii(valor)
    return texto[:80] + (" [...]" if len(texto) > 80 else "")


def problema_do_caminho(partes) -> str | None:
    """None se `partes` (o caminho dentro do plugin) é `skills/<skill>/scripts/<arquivo>.py` ou
    `skills/<skill>/requirements.lock` na forma; senão o motivo."""
    n = len(partes)
    if n >= 3 and partes[0] == "skills" and NOME_DA_SKILL.fullmatch(partes[1]):
        if (n == 4 and partes[2] == "scripts" and ARQUIVO_DO_SCRIPT.fullmatch(partes[3])) \
                or (n == 3 and partes[2] == "requirements.lock"):
            return None
    return ("script só em skills/<skill>/scripts/<nome>.py (nome em minúsculas, números e sublinhado, até 32) e o lock "
            "só em skills/<skill>/requirements.lock, com a skill em minúsculas, números e hífen")


def sem_item(partes) -> str | None:
    """O motivo do `.py` que está no lugar certo mas não tem item na ficha (o `.py` fora do lugar, ou de outro tipo, fica
    com a recusa geral do aberturas_plugins); None nos outros casos."""
    if partes[-1].endswith(".py") and problema_do_caminho(partes) is None:
        return ("script sem item em skills_com_scripts da ficha: só na 1.7.11 e só listado, com o SHA-256 e o modo dele "
                "(a ficha lista também o SKILL.md e, se houver pacotes, o lock)")
    return None


# ------------------------------------------------------------------ o requirements.lock
def _porque(bloco: str) -> str:
    primeira = re.sub(r" \\$", "", bloco.split("\n")[0].strip())
    if primeira.startswith("-"):
        return "opção de pip (-e, -r, -c, -f, --index-url...): o lock só leva pacotes com hash"
    if re.search(r"://|\s@\s|^[./~]|[/\\]|;", primeira):
        return "URL, caminho ou marcador de ambiente: o lock só leva nome==versão"
    if "==" not in primeira:
        return "pacote sem versão fixa (nome==versão)"
    if "--hash=sha256:" not in bloco:
        return "pacote sem --hash=sha256:<64 dígitos> (uma linha de continuação por hash)"
    return "linha fora da forma nome==versão com --hash=sha256:<64>"


def ler_lock(dados: bytes) -> tuple[list[str], list[str]]:
    """(motivos, nomes) do requirements.lock: ASCII, até TETO_LOCK bytes, só comentários em linha própria e pacotes
    `nome==versão` com um ou mais `--hash=sha256:` (a forma de `_PACOTE`), até TETO_PACOTES, sem pacote repetido. Os
    nomes vêm normalizados (minúsculas, hífen). Nada de opção, URL ou caminho."""
    if len(dados) > TETO_LOCK:
        return [f"requirements.lock acima de {TETO_LOCK} bytes"], []
    try:
        texto = dados.decode("ascii").replace("\r\n", "\n")
    except UnicodeDecodeError:
        return ["requirements.lock só em ASCII"], []
    if re.search(r"[^\x20-\x7e\n]", texto):
        return ["requirements.lock com caractere de controle, tab ou CR sozinho"], []
    motivos, nomes, linhas, i = [], [], texto.split("\n"), 0
    while i < len(linhas):
        bloco, i = linhas[i], i + 1
        if not bloco.strip() or bloco.lstrip().startswith("#"):
            continue
        while bloco.endswith(" \\") and i < len(linhas):
            bloco, i = bloco + "\n" + linhas[i], i + 1
        achado = _PACOTE.fullmatch(bloco)
        nome = re.sub(r"[-_.]+", "-", achado.group(1)).lower() if achado else None
        if achado is None:
            motivos.append(f"{_porque(bloco)}: {_mostrar(bloco.split(chr(10))[0][:60])}")
        elif nome in nomes:
            motivos.append(f"pacote repetido: {nome}")
        else:
            nomes.append(nome)
    if len(nomes) > TETO_PACOTES:
        motivos.append(f"mais de {TETO_PACOTES} pacotes no lock")
    if not nomes and not motivos:
        motivos.append("lock sem pacote (sem dependências, tire o campo dependencias da ficha)")
    return motivos[:8] + ([f"(e mais {len(motivos) - 8} problemas)"] if len(motivos) > 8 else []), nomes


def conferir_lock(rel: str, dados: bytes, erro) -> None:
    for motivo in ler_lock(dados)[0]:
        erro(rel, motivo)


# ------------------------------------------------------------------ a ficha
def _script(R, sc, campo: str, skill, vistos: set, erro) -> None:
    if not isinstance(sc, dict) or set(sc) != set(CAMPOS_DO_SCRIPT):
        erro(campo, "cada script é {" + ", ".join(CAMPOS_DO_SCRIPT) + "}, sem outros campos")
        return
    nome, caminho, sha, modo = (sc[c] for c in CAMPOS_DO_SCRIPT)
    if not isinstance(nome, str) or not NOME_DO_SCRIPT.fullmatch(nome) or nome in vistos["nomes"]:
        erro(campo + ".nome", "nome do script em minúsculas, números e hífen (até 32), sem repetir na skill",
             valor=R.mostrar(nome))
    else:
        vistos["nomes"].add(nome)
    partes = caminho.split("/") if isinstance(caminho, str) else []
    if (not partes or problema_do_caminho(partes) or len(partes) != 4 or partes[1] != skill
            or caminho in vistos["caminhos"]):
        erro(campo + ".caminho", f"exatamente skills/{skill if isinstance(skill, str) else '<skill>'}/scripts/<arquivo>.py"
             " (arquivo em minúsculas, números e sublinhado), sem repetir", valor=R.mostrar(caminho))
    else:
        vistos["caminhos"].add(caminho)
        if isinstance(nome, str) and NOME_DO_SCRIPT.fullmatch(nome) and nome != partes[3][:-3].replace("_", "-"):
            erro(campo + ".nome", "o nome do script é o do arquivo sem .py, com _ trocado por -: o que o titular vê é o "
                 "que roda", valor=R.mostrar(nome))
    if not isinstance(sha, str) or not SHA256.fullmatch(sha):
        erro(campo + ".sha256", "SHA-256 do script (64 dígitos hexadecimais minúsculos)")
    if modo not in MODOS:
        erro(campo + ".modo", "modo: " + ", ".join(MODOS), valor=R.mostrar(modo))
    elif modo not in MODOS_ABERTOS:
        erro(campo + ".modo", "modo caixa: 1.7.11, lote S4 (a caixa sem rede ainda não está instalada)", versao="1.7.11")


def _dependencias(R, dep, skill, campo: str, erro) -> None:
    if not isinstance(dep, dict) or set(dep) != set(CAMPOS_DAS_DEPENDENCIAS):
        erro(campo, "dependencias é {" + ", ".join(CAMPOS_DAS_DEPENDENCIAS) + "}, sem outros campos")
        return
    if not isinstance(skill, str) or dep["lock"] != f"skills/{skill}/requirements.lock":
        erro(campo + ".lock", "exatamente skills/<skill>/requirements.lock da mesma skill", valor=R.mostrar(dep["lock"]))
    if not isinstance(dep["lock_sha256"], str) or not SHA256.fullmatch(dep["lock_sha256"]):
        erro(campo + ".lock_sha256", "SHA-256 do lock (64 dígitos hexadecimais minúsculos)")
    rodas = dep["rodas"]
    motivo = R.problema_da_origem(rodas)
    if motivo is None and rodas.split("/")[0].casefold() == "plugins-candidatos":
        motivo = "as rodas ficam fora do candidato (por exemplo em outputs/): dentro dele entrariam no manifesto"
    if motivo:
        erro(campo + ".rodas", motivo, valor=R.mostrar(rodas))
    if dep["python"] not in PYTHONS:
        erro(campo + ".python", "versão do Python medida no Ubuntu: " + ", ".join(PYTHONS), valor=R.mostrar(dep["python"]))
    pacotes = dep["pacotes"]
    if isinstance(pacotes, bool) or not isinstance(pacotes, int) or not 1 <= pacotes <= TETO_PACOTES:
        erro(campo + ".pacotes", f"número de pacotes do lock, de 1 a {TETO_PACOTES}", valor=R.mostrar(pacotes))


def _skill(R, s, campo: str, vistas: set, erro) -> int:
    if not isinstance(s, dict) or not set(CAMPOS_DA_SKILL) <= set(s) <= {*CAMPOS_DA_SKILL, "dependencias"}:
        erro(campo, "cada skill é {" + ", ".join(CAMPOS_DA_SKILL) + "} e, se usar pacotes, dependencias; sem outros campos")
        return 0
    skill = s["skill"]
    if not isinstance(skill, str) or not NOME_DA_SKILL.fullmatch(skill) or skill in vistas:
        erro(campo + ".skill", "pasta de skills/ do plugin em minúsculas, números e hífen, uma vez só no plugin",
             valor=R.mostrar(skill))
    else:
        vistas.add(skill)
    if not isinstance(s["skill_md_sha256"], str) or not SHA256.fullmatch(s["skill_md_sha256"]):
        erro(campo + ".skill_md_sha256", "SHA-256 do SKILL.md da skill (64 dígitos hexadecimais minúsculos)")
    scripts, vistos = s["scripts"], {"nomes": set(), "caminhos": set()}
    if not isinstance(scripts, list) or not 1 <= len(scripts) <= TETO_SCRIPTS_SKILL:
        erro(campo + ".scripts", f"lista de 1 a {TETO_SCRIPTS_SKILL} scripts")
        scripts = []
    for k, sc in enumerate(scripts):
        _script(R, sc, f"{campo}.scripts[{k}]", skill, vistos, erro)
    if "dependencias" in s:
        _dependencias(R, s["dependencias"], skill, campo + ".dependencias", erro)
    return len(scripts)


def validar(R, ficha: dict, hoje, erro, avisos: list) -> None:
    plugins = ficha.get("plugins")
    if not isinstance(plugins, list):
        return
    projeto = ficha.get("project_id") if isinstance(ficha.get("project_id"), str) else None
    skills = scripts = 0
    for i, item in enumerate(plugins):
        if not isinstance(item, dict) or "skills_com_scripts" not in item:
            continue
        campo, lista = f"plugins[{i}].skills_com_scripts", item["skills_com_scripts"]
        if not isinstance(lista, list) or len(lista) > TETO_SKILLS_PLUGIN:
            erro(campo, f"lista de até {TETO_SKILLS_PLUGIN} skills (vazia ou ausente: nenhum script abre)")
            continue
        nome = item.get("nome")
        if lista and projeto and isinstance(nome, str) and not nome.startswith(projeto + "-"):
            erro(f"plugins[{i}].nome", f"plugin com scripts tem de se chamar {projeto}-<nome>: a skill vira "
                 "<plugin>:<skill> e o prefixo do projeto evita o choque de nomes entre projetos", valor=R.mostrar(nome))
        vistas: set = set()
        scripts += sum(_skill(R, s, f"{campo}[{j}]", vistas, erro) for j, s in enumerate(lista))
        skills += len(lista)
    if skills > TETO_SKILLS_FICHA:
        erro("plugins", f"mais de {TETO_SKILLS_FICHA} skills com scripts na ficha")
    if scripts > TETO_SCRIPTS_FICHA:
        erro("plugins", f"mais de {TETO_SCRIPTS_FICHA} scripts na ficha")


def _skills(ficha):
    """(plugin, skill) de cada skill com scripts da ficha na forma de dicionário; o resto (ficha adulterada) fica de fora."""
    lista = ficha.get("plugins") if isinstance(ficha, dict) else None
    for p in lista if isinstance(lista, list) else []:
        for s in (p.get("skills_com_scripts") if isinstance(p, dict) and isinstance(p.get("skills_com_scripts"), list)
                  else []):
            if isinstance(s, dict):
                yield p, s


def _scripts(s) -> list[dict]:
    return [sc for sc in s.get("scripts") if isinstance(sc, dict)] if isinstance(s.get("scripts"), list) else []


def _dep(s) -> dict | None:
    return s["dependencias"] if isinstance(s.get("dependencias"), dict) else None


def itens(ficha) -> list[tuple[str, str]]:
    """Cada script e cada lista de pacotes como (seção, item), com o início do SHA-256: arquivo trocado aparece como o que
    fecha e o que abre."""
    saida = []
    for p, s in _skills(ficha):
        saida += [("scripts", f"{p.get('nome')}:{s.get('skill')}/{sc.get('nome')} (SHA-256 {str(sc.get('sha256'))[:12]})")
                  for sc in _scripts(s)]
        if dep := _dep(s):
            saida.append(("dependencias", f"{p.get('nome')}:{s.get('skill')} ({dep.get('pacotes')} pacotes, lock SHA-256 "
                                          f"{str(dep.get('lock_sha256'))[:12]})"))
    return saida


def descrever(R, ficha) -> list[dict]:
    saida = []
    for p, s in _skills(ficha):
        for sc in _scripts(s):
            item = R.mostrar(f"{p.get('nome')}:{s.get('skill')}/{sc.get('nome')}")
            sha, caminho = str(sc.get("sha256"))[:8], R.mostrar(sc.get("caminho"))
            if sc.get("modo") == "caixa":
                texto = (f"O script {caminho} (SHA-256 {sha}…) é um PROGRAMA. Roda numa caixa sem rede, que vê só os "
                         "arquivos do projeto listados em cada pedido e grava só numa pasta nova de outputs/.")
            else:
                texto = (f"O script {caminho} (SHA-256 {sha}…) da skill {R.mostrar(s.get('skill'))} é um PROGRAMA. Roda "
                         "pelo executor da fundação, com a mesma autoridade dos comandos da sessão: lê e grava o que eles "
                         "alcançam (com a raiz em /mnt/e, também fora do projeto) e usa a rede da ficha. A fundação "
                         "confere que é o arquivo assinado, não o que ele faz.")
            saida.append({"secao": "scripts", "item": item, "texto": texto})
        if dep := _dep(s):
            saida.append({"secao": "dependencias", "item": R.mostrar(f"{p.get('nome')}:{s.get('skill')}"),
                          "texto": f"A skill {R.mostrar(s.get('skill'))} usa {R.mostrar(dep.get('pacotes'))} pacotes de "
                                   f"terceiros (lista no requirements.lock, SHA-256 {str(dep.get('lock_sha256'))[:8]}…), "
                                   "instalados pelo preparo numa pasta de dono root. O código deles roda junto com o "
                                   "script. O hash prova que são os pacotes baixados, não que são seguros."})
    return saida


# ------------------------------------------------------------------ o plugin no disco (aberturas_plugins)
def caminhos(skills) -> frozenset:
    """Os caminhos que a ficha lista (cada script e cada lock): só esses `.py` e `requirements.lock` podem entrar no
    plugin. Item fora da forma (ficha adulterada) fica de fora e é problema de `conferir_no_disco`."""
    saida = set()
    for s in skills if isinstance(skills, list) else []:
        if isinstance(s, dict):
            saida |= {sc["caminho"] for sc in _scripts(s) if isinstance(sc.get("caminho"), str)}
            if (dep := _dep(s)) and isinstance(dep.get("lock"), str):
                saida.add(dep["lock"])
    return frozenset(saida)


def conferir_no_disco(plugin: str | None, skills, arquivos: list, lidos: dict) -> list[dict]:
    """A lista da ficha contra o plugin já conferido (`arquivos`: o manifesto; `lidos`: os bytes lidos do `.py` e do lock,
    os mesmos do hash): o `SKILL.md`, cada script e o lock existem e têm o SHA-256 da ficha, o lock está na forma e tem
    `pacotes` pacotes, e nenhum arquivo de código ficou sem item. Cada problema: {campo, motivo}. Ficha fora da forma ou
    arquivo não lido: problema, nunca exceção."""
    erros: list[dict] = []

    def erro(rel, motivo, **extra):
        erros.append({"campo": f"plugin {plugin or ''}: {rel}", "motivo": motivo, **extra})
    if not isinstance(skills, list) or not all(isinstance(s, dict) for s in skills):
        erro("skills_com_scripts", "skills_com_scripts da ficha fora da forma (lista de objetos)")
        return erros
    manifesto, listados = {a["caminho"]: a["sha256"] for a in arquivos}, set()
    for s in skills:
        skill = s.get("skill")
        md = f"skills/{skill}/SKILL.md"
        if not isinstance(skill, str) or not NOME_DA_SKILL.fullmatch(skill) or md not in manifesto:
            erro(md, "a skill da ficha não tem skills/<skill>/SKILL.md no plugin")
            continue
        if manifesto[md] != s.get("skill_md_sha256"):
            erro(md, "o SHA-256 do SKILL.md difere de skill_md_sha256 da ficha: prepare a ficha de novo",
                 calculado=manifesto[md])
        for sc in _scripts(s):
            rel = sc.get("caminho")
            if not isinstance(rel, str) or rel not in manifesto or problema_do_caminho(rel.split("/")) \
                    or rel.split("/")[1] != skill or not rel.endswith(".py"):
                erro(_mostrar(rel), "o script da ficha não está no plugin em skills/<skill>/scripts/<arquivo>.py")
            elif manifesto[rel] != sc.get("sha256"):
                erro(rel, "o SHA-256 do script difere de scripts[].sha256 da ficha: prepare a ficha de novo",
                     calculado=manifesto[rel])
            else:
                listados.add(rel)
        if (dep := _dep(s)) is None:
            continue
        lock = f"skills/{skill}/requirements.lock"
        if dep.get("lock") != lock or lock not in manifesto:
            erro(lock, "o lock da ficha não está no plugin em skills/<skill>/requirements.lock")
        elif manifesto[lock] != dep.get("lock_sha256"):
            erro(lock, "o SHA-256 do lock difere de dependencias.lock_sha256 da ficha: prepare a ficha de novo",
                 calculado=manifesto[lock])
        else:
            listados.add(lock)
            motivos, nomes = ler_lock(lidos.get(lock, b""))
            for motivo in motivos:
                erro(lock, motivo)
            if not motivos and len(nomes) != dep.get("pacotes"):
                erro(lock, f"o lock tem {len(nomes)} pacotes e a ficha diz {_mostrar(dep.get('pacotes'))}")
    erros += [{"campo": f"plugin {plugin or ''}: {rel}", "motivo": "arquivo de código do plugin fora de "
               "skills_com_scripts da ficha"} for rel in sorted(set(lidos) - listados) if not erros]
    return erros
