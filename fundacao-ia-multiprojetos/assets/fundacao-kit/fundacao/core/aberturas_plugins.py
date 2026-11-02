"""Plugins da ficha de aberturas no disco (1.7.10; contratos do lote 2, §5 e §8; crítica do desenho, §8.2: conferir por
lista positiva, frontmatter só com chaves permitidas, "sem hooks, mcpServers, permissionMode nem `!`").

Na 1.7.10 um plugin candidato (montado pela sessão em `projects/<p>/plugins-candidatos/<p>-<nome>/`, DESENHO-1.7.10
§8.2) só vale com: `.claude-plugin/plugin.json` sem `hooks`, `mcpServers` nem `lspServers` e só com os campos de
descrição (CAMPOS_DO_MANIFESTO); Markdown em `skills/`, `agents/` e `commands/`; README, LICENSE e CHANGELOG na raiz.
Pasta `hooks/`, `.mcp.json`, executável ou script (pela extensão e, fora do Windows, pelo bit de execução): recusa
"1.7.11". Numa montagem 9p ou drvfs sem a opção metadata (o DrvFs do WSL, /mnt/<letra>), todo arquivo aparece 0777 e o
bit não prova nada: lá vale o conteúdo (`#!`, ELF ou MZ no começo), sem recusar pelo bit (emenda E9;
`bit_de_execucao_vale` lê o /proc/mounts, sem executar programa, e acha a montagem pelo objeto aberto, não pelo caminho,
que uma ligação posta depois da abertura desviaria); no ext4 e no Windows, a regra de antes. Ligação, vínculo físico,
dispositivo ou FIFO: recusa. Nome que não é UTF-8, nome forte e pasta de segredo da regra única (as listas de
core/manutencao.py, iguais às de scripts/regras_de_segredo.py por teste, comparadas como a regra única compara: NFKC,
sem caixa, a barra invertida como separador): recusa sem ler, nem para o hash (integração, item I16: as recusas do
scripts/plugin_candidato.py no caminho confiável). Nome que muda entre o Windows e o Ubuntu (`_nome_que_muda`): com
caractere da área privada do Unicode, que o DrvFs troca por controle ou `" * : < > ? \\ |`, com um destes ou terminado
em ponto ou espaço: recusa sem ler, para o mesmo candidato dar o mesmo resultado nos dois sistemas (reconferência da
integração, rodada 2). Cada Markdown passa por core/aberturas_markdown.py: texto,
cabeçalho, allowed-tools e menção `@` (emendas E4 e E8; item I16); a licença da raiz que não é Markdown, pelo
`conferir_texto` de lá (texto UTF-8 sem controle; revisão da integração, rodada 2). O manifesto (caminho, tamanho e
SHA-256 de cada arquivo) prende o conteúdo: o titular assina o `manifesto_sha256` na ficha, e o preparo do host
confere a cópia por ele (scripts/copia_segura.py, com o SHA-256 de cada arquivo).

A leitura é a de core/aberturas_disco.py (a pasta aberta por descritor no POSIX; no Windows, pelo caminho conferido):
`ler_arquivo`, `LeituraRecusada` e `e_ligacao` ficam também aqui, com os nomes de sempre, como os de
core/aberturas_markdown.py que já moravam aqui (CHAVES_DO_FRONTMATTER e as expressões do texto).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import unicodedata
from fnmatch import fnmatchcase
from pathlib import Path

from .aberturas_disco import LeituraRecusada, Pasta, e_ligacao, ler_arquivo  # noqa: F401 (reexportados)
from .aberturas_markdown import (CHAVES_DO_FRONTMATTER, _CONTEXTO_DINAMICO, _CONTROLE,  # noqa: F401 (reexportados)
                                 _QUEBRA_ESCONDIDA, conferir_markdown, conferir_texto)
from .aberturas_regras import PASTAS_PROTEGIDAS, carregar, mostrar, problema_da_origem
from .contracts import PathEscape
from .manutencao import NOMES_DE_SEGREDO, PASTAS_DE_SEGREDO

TETO_PLUGIN = {"arquivos": 500, "bytes_arquivo": 1 << 20, "bytes": 16 << 20, "niveis": 12}
PASTAS_DO_PLUGIN = frozenset({".claude-plugin", "skills", "agents", "commands"})
NA_RAIZ_DO_PLUGIN = frozenset({"readme.md", "license", "license.md", "license.txt", "changelog.md"})
CAMPOS_DO_MANIFESTO = frozenset({"name", "version", "description", "author", "homepage", "repository", "license",
                                 "keywords"})
SO_NA_1711 = ("hooks", "mcpServers", "lspServers")
EXECUTAVEIS = frozenset(".py .pyw .pyc .sh .bash .zsh .fish .ps1 .psm1 .bat .cmd .com .exe .dll .so .dylib .js .mjs "
                        ".cjs .ts .rb .pl .php .jar .bin .vbs .wsf .msi .scr".split())
# Regra única de segredo (contratos §3; item I16): fortes + pastas, como a regra única compara (NFKC e sem caixa). Sem a
# exceção dos exemplos (`*.example`, `*.sample`): no plugin, um arquivo assim já recusa pelo tipo, e uma pasta assim
# com nome forte recusa aqui (mais estrito; o plugin_candidato a recusa também, pela regra do kit, por último).
_PASTAS_DE_SEGREDO = frozenset(unicodedata.normalize("NFKC", p).casefold() for p in PASTAS_DE_SEGREDO)
_NOMES_FORTES = tuple(unicodedata.normalize("NFKC", g).casefold() for g in NOMES_DE_SEGREDO)
# Emenda E9: as montagens em que o bit de execução não prova nada (sem a opção metadata) e o que o Linux executa pelo
# conteúdo: script com `#!`, binário ELF e o MZ do Windows, que o WSL executa pela interoperação (binfmt).
MONTAGENS = "/proc/mounts"
TIPOS_SEM_BIT = frozenset({"9p", "drvfs"})
ASSINATURAS_DE_EXECUTAVEL = (b"#!", b"\x7fELF", b"MZ")
# Nome que muda entre o Windows e o Ubuntu (reconferência da integração, rodada 2; sondado no DrvFs em 01/11/2026): o
# DrvFs (/mnt/<letra> no WSL) guarda os controles e " * : < > ? \ | de um nome do Ubuntu como U+F000 mais o código
# (área privada do Unicode), que é o que o Windows vê; e um nome do Windows com esses caracteres da área privada aparece
# no Ubuntu com o caractere de volta (o U+F000 vira NUL e corta o nome). O Windows também não abre pelo nome o que
# termina em ponto ou espaço (o Win32 os tira). O mesmo candidato teria outra recusa ou outro manifesto em cada lado:
# as duas faces recusam.
_FACE_DO_UBUNTU = re.compile(r'[\x00-\x1f"*:<>?\\|]|[. ]\Z')


def sha256_do_manifesto(arquivos: list[dict]) -> str:
    """SHA-256 do manifesto do plugin: a lista {caminho, bytes, sha256} em ordem de caminho, em JSON compacto com as
    chaves ordenadas e UTF-8 (a mesma receita no preparo, na ferramenta do titular e no preparo do host)."""
    lista = sorted(({"caminho": a["caminho"], "bytes": a["bytes"], "sha256": a["sha256"]} for a in arquivos),
                   key=lambda a: a["caminho"])
    return hashlib.sha256(json.dumps(lista, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()


def _segredo_no_nome(nome: str) -> str | None:
    """A regra única sobre o nome de uma entrada do plugin, como o plugin_candidato a aplica (regras_de_segredo.
    classificar): pasta de segredo em qualquer parte do nome, nome forte na última (a barra invertida separa)."""
    partes = [unicodedata.normalize("NFKC", p).casefold() for p in nome.replace("\\", "/").split("/")
              if p not in ("", ".")]
    if any(p in _PASTAS_DE_SEGREDO for p in partes):
        return "pasta de segredo da regra única: recusada sem ler nem listar o que tem dentro"
    if partes and any(fnmatchcase(partes[-1], g) for g in _NOMES_FORTES):
        return "nome forte de segredo da regra única (chave, credencial ou cofre): recusado sem ler, nem para o hash"
    return None


def _nome_que_muda(nome: str) -> str | None:
    """O nome de uma entrada do plugin que o DrvFs mostra diferente no Windows e no Ubuntu, ou que o Windows não abre
    pelo nome (`_FACE_DO_UBUNTU`): a face do Windows (área privada do Unicode, toda ela) e a do Ubuntu."""
    if any(unicodedata.category(c) == "Co" for c in nome):
        return ("caractere da área privada do Unicode no nome: o DrvFs (/mnt/<letra> no WSL) o troca por controle ou "
                '" * : < > ? \\ |, e o mesmo arquivo teria outro nome (e outro manifesto) no Ubuntu: recusado sem ler')
    if _FACE_DO_UBUNTU.search(nome):
        return ('nome que não funciona igual no Windows e no Ubuntu (controle, " * : < > ? \\ |, ponto ou espaço no '
                "fim): no DrvFs, o Windows o vê com outro nome ou não o abre; recusado sem ler")
    return None


def bit_vale_na_montagem(alvo: str, montagens: str) -> bool:
    """Pelo texto do /proc/mounts: o bit de execução prova executável em `alvo` (caminho absoluto, já resolvido)? Vale
    a montagem do ponto mais longo que contém `alvo`, componente a componente (no empate, a linha de baixo, que é a de
    cima); False só se ela é 9p ou drvfs sem a opção metadata (as opções vão por vírgula e, no aname do 9p, por ponto e
    vírgula). O ponto vem sem os escapes octais do kernel (\\040 é o espaço)."""
    ponto, tipo, opcoes = "", "", ""
    for linha in montagens.splitlines():
        campos = linha.split()
        if len(campos) < 4:
            continue
        candidato = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), campos[1])
        if (alvo == candidato or alvo.startswith(candidato.rstrip("/") + "/")) and len(candidato) >= len(ponto):
            ponto, tipo, opcoes = candidato, campos[2], " ".join(campos[3:-2] if len(campos) >= 6 else campos[3:])
    return not (tipo in TIPOS_SEM_BIT and "metadata" not in re.split(r"[,;]", opcoes))


def _onde_esta(pasta) -> str:
    """O caminho em que se procura a montagem de `pasta` (um caminho ou uma Pasta aberta): com a Pasta aberta por
    descritor (POSIX), o do objeto aberto (/proc/self/fd/<fd>), que trocar um componente do caminho por ligação depois
    da abertura não desvia (revisão da integração, rodada 2: o realpath do caminho seguia a ligação, e uma pasta do ext4
    passava por DrvFs, sem o bit); sem descritor, o caminho resolvido."""
    fd = getattr(pasta, "_fd", None)
    if fd is not None:
        try:
            return os.readlink(f"/proc/self/fd/{fd}")
        except OSError:
            pass
    return os.path.realpath(getattr(pasta, "caminho", pasta))


def bit_de_execucao_vale(pasta, montagens: str | None = None) -> bool:
    """Emenda E9: fora do Windows, o bit de execução prova executável em `pasta` (um caminho ou uma Pasta aberta,
    `_onde_esta`), salvo numa montagem 9p ou drvfs sem a opção metadata. Lê o /proc/mounts (MONTAGENS), sem executar
    programa; sem ele (outro sistema), True: a regra de antes. `montagens`: o texto, no lugar do arquivo (testes)."""
    if montagens is None:
        try:
            with open(MONTAGENS, "rb") as arquivo:
                montagens = arquivo.read(1 << 20).decode("utf-8", "surrogateescape")
        except OSError:
            return True
    return bit_vale_na_montagem(_onde_esta(pasta), montagens)


def executavel_pelo_conteudo(dados: bytes) -> bool:
    """Emenda E9: o arquivo começa como o que o Linux (e o WSL, pela interoperação) executa: `#!`, ELF ou MZ."""
    return dados.startswith(ASSINATURAS_DE_EXECUTAVEL)


def _problema_do_arquivo(partes: tuple, st: os.stat_result, pelo_conteudo: bool) -> tuple[str | None, str | None]:
    baixo = partes[-1].casefold()
    if baixo == ".mcp.json":
        return "servidor MCP no plugin: só na 1.7.11 (MCP de terceiro roda fora do sandbox)", "1.7.11"
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
        return "não é arquivo comum de um nome só (dispositivo, FIFO ou vínculo físico)", None
    if os.path.splitext(baixo)[1] in EXECUTAVEIS:
        return "executável ou script no plugin: só na 1.7.11", "1.7.11"
    if os.name != "nt" and not pelo_conteudo and st.st_mode & 0o111:  # o porquê vai no motivo (revisão, defeito 5)
        return ("executável ou script no plugin: só na 1.7.11 (bit de execução; no DrvFs sem a opção metadata, como "
                "/mnt/<letra> no WSL, o bit não prova nada e vale o conteúdo)"), "1.7.11"
    if len(partes) == 1:
        return (None, None) if baixo in NA_RAIZ_DO_PLUGIN else ("arquivo fora do formato aceito na 1.7.10", None)
    if partes[0] == ".claude-plugin":
        if partes == (".claude-plugin", "plugin.json"):
            return None, None
        return "só o plugin.json em .claude-plugin/", None
    return (None, None) if baixo.endswith(".md") else ("só Markdown em skills/, agents/ e commands/ na 1.7.10", None)


def _manifesto(rel: str, dados: bytes, nome: str | None, erro) -> None:
    try:
        manifesto = carregar(dados)
    except ValueError:
        manifesto = None
    if not isinstance(manifesto, dict):
        erro(rel, "manifesto do plugin ilegível")
        return
    proibidos = [c for c in SO_NA_1711 if c in manifesto]
    if proibidos:
        erro(rel, ", ".join(proibidos) + " no manifesto: só na 1.7.11", "1.7.11")
    outros = sorted(set(manifesto) - CAMPOS_DO_MANIFESTO - set(SO_NA_1711))
    if outros:
        erro(rel, "campo do manifesto fora do aceito na 1.7.10: " + ", ".join(mostrar(o) for o in outros))
    if nome is not None and manifesto.get("name") != nome:
        erro(rel, "o name do manifesto difere do nome do plugin na ficha")


class _AcimaDoTeto(Exception):
    """O plugin passou do teto de arquivos ou de bytes: a varredura para."""


def _percorrer(pasta: Pasta, partes: tuple, estado: dict, erro) -> None:
    """Uma pasta do plugin, pelo descritor dela (no POSIX), e as de baixo, em profundidade: no máximo uma pasta aberta
    por nível. Nome fora do UTF-8 e segredo da regra única recusam antes de qualquer exame ou leitura (item I16), e o
    nome que muda entre o Windows e o Ubuntu também, depois da regra única (a barra invertida, que é a face do U+F05C
    no Ubuntu, continua separando, e a pasta de segredo fica com o motivo dela; reconferência da integração,
    rodada 2)."""
    try:
        nomes = pasta.nomes()
    except OSError:
        erro("/".join(partes), "pasta ilegível")
        return
    for n in nomes:
        if any("\ud800" <= c <= "\udfff" for c in n):  # bytes fora do UTF-8 (POSIX) ou surrogate solto (Windows)
            visto = n.encode("utf-8", "backslashreplace").decode("utf-8")
            erro("/".join(partes + (visto,)), "nome que não é UTF-8: recusado sem ler (o manifesto e a ficha são "
                                                "UTF-8)")
            continue
        rel_partes = partes + (n,)
        rel = "/".join(rel_partes)
        if motivo := _segredo_no_nome(n) or _nome_que_muda(n):
            erro(rel, motivo)
            continue
        try:
            st = pasta.lstat(n)
        except OSError:
            erro(rel, "ilegível")
            continue
        if e_ligacao(st):
            erro(rel, "ligação (link simbólico ou junção) dentro do plugin")
        elif stat.S_ISDIR(st.st_mode):
            if not partes and n not in PASTAS_DO_PLUGIN:
                hooks = n.casefold() == "hooks"
                erro(rel, "hooks no plugin: só na 1.7.11" if hooks else "pasta fora do formato aceito na 1.7.10 "
                     "(.claude-plugin, skills, agents, commands)", "1.7.11" if hooks else None)
            elif len(rel_partes) > TETO_PLUGIN["niveis"]:
                erro(rel, "plugin fundo demais")
            else:
                try:
                    filha = pasta.sub(n)
                except (PathEscape, OSError):
                    erro(rel, "pasta trocada por ligação ou ilegível durante a conferência")
                    continue
                with filha:
                    _percorrer(filha, rel_partes, estado, erro)
            continue
        motivo, versao = _problema_do_arquivo(rel_partes, st, estado["pelo_conteudo"])
        if motivo:
            erro(rel, motivo, versao)
            continue
        try:
            dados = pasta.ler(n, TETO_PLUGIN["bytes_arquivo"])
        except OSError as exc:
            erro(rel, f"não lido ({exc.__class__.__name__})")
            continue
        if dados is None:
            erro(rel, "sumiu durante a conferência")
            continue
        if estado["pelo_conteudo"] and executavel_pelo_conteudo(dados):
            erro(rel, "executável ou script no plugin pelo conteúdo (#!, ELF ou MZ no começo; numa montagem 9p ou "
                      "drvfs sem a opção metadata o bit de execução não prova nada): só na 1.7.11", "1.7.11")
            continue
        estado["bytes"] += len(dados)
        if estado["bytes"] > TETO_PLUGIN["bytes"] or len(estado["arquivos"]) >= TETO_PLUGIN["arquivos"]:
            erro("", "plugin acima do teto de arquivos ou de bytes")
            raise _AcimaDoTeto
        estado["arquivos"].append({"caminho": rel, "bytes": len(dados), "sha256": hashlib.sha256(dados).hexdigest()})
        if rel_partes == (".claude-plugin", "plugin.json"):
            _manifesto(rel, dados, estado["nome"], erro)
        elif n.casefold().endswith(".md"):  # o conteúdo, em todo Markdown; o cabeçalho, só fora da raiz do plugin
            conferir_markdown(rel_partes, dados, erro)
            if rel_partes[0] == "skills" and len(rel_partes) == 3 and n == "SKILL.md":
                estado["skills"].add(rel_partes[1])
            elif rel_partes[0] in ("agents", "commands"):
                estado["agentes" if rel_partes[0] == "agents" else "comandos"].add(rel[len(rel_partes[0]) + 1:-3])
        else:  # só sobra a licença da raiz que não é Markdown (LICENSE, LICENSE.txt): texto, como no plugin_candidato
            conferir_texto(rel, dados, erro)


def _conferir_aberta(pasta: Pasta, nome: str | None) -> dict:
    erros = []
    estado = {"nome": nome, "bytes": 0, "arquivos": [], "skills": set(), "agentes": set(), "comandos": set(),
              "pelo_conteudo": False}

    def erro(rel, motivo, versao=None):
        erros.append({"campo": f"plugin {nome or ''}: {rel or '.'}", "motivo": motivo,
                      **({"versao": versao} if versao else {})})
    if not pasta.existe:
        erro("", "pasta do plugin ausente, ligação ou não é pasta")
    else:
        estado["pelo_conteudo"] = os.name != "nt" and not bit_de_execucao_vale(pasta)  # emenda E9, pelo objeto aberto
        try:
            _percorrer(pasta, (), estado, erro)
        except _AcimaDoTeto:
            pass
    arquivos = sorted(estado["arquivos"], key=lambda a: a["caminho"])
    if not erros and not any(a["caminho"] == ".claude-plugin/plugin.json" for a in arquivos):
        erro(".claude-plugin/plugin.json", "plugin sem manifesto")
    return {"erros": erros, "arquivos": arquivos, "manifesto_sha256": None if erros else sha256_do_manifesto(arquivos),
            **{k: sorted(estado[k]) for k in ("skills", "agentes", "comandos")}}


class _Ausente:
    existe = False


def conferir_pasta_do_plugin(pasta, nome: str | None = None) -> dict:
    """Confere no disco a pasta de um plugin candidato (sem seguir ligação) e calcula o manifesto. Devolve `erros`,
    `arquivos` ({caminho, bytes, sha256}), `manifesto_sha256` (None se houve erro), `skills`, `agentes` e
    `comandos`."""
    pasta = Path(pasta)
    try:
        with Pasta(pasta.parent, (pasta.name,)) as aberta:
            return _conferir_aberta(aberta, nome)
    except (PathEscape, OSError):
        return _conferir_aberta(_Ausente(), nome)


def conferir_plugin(pasta_projeto, item: dict) -> dict:
    """Um item `plugins[]` da ficha no disco: a origem desce da pasta do projeto sem passar por ligação (no POSIX, pelo
    descritor de cada pasta), resolve dentro dela e fora das pastas protegidas e confere com o `manifesto_sha256`
    (quando já vem preenchido)."""
    def recusa(motivo):
        return {"erros": [{"campo": "origem", "motivo": motivo}], "arquivos": [], "manifesto_sha256": None}
    motivo = problema_da_origem(item.get("origem")) if isinstance(item, dict) else "plugin fora do formato"
    if motivo:
        return recusa(motivo)
    base, origem = Path(pasta_projeto), item["origem"]
    nome = item.get("nome") if isinstance(item.get("nome"), str) else None
    try:
        with Pasta(base, tuple(origem.split("/"))) as aberta:
            if not aberta.existe:
                return recusa("origem do plugin ausente: " + mostrar(origem))
            try:  # o caminho resolvido (no Windows, também o nome curto 8.3 e o ponto final): dentro e fora de data/
                rel = Path(os.path.realpath(aberta.caminho)).relative_to(os.path.realpath(base))
            except ValueError:
                return recusa("origem do plugin fora da pasta do projeto")
            if not rel.parts or rel.parts[0].casefold() in PASTAS_PROTEGIDAS:
                return recusa("origem do plugin resolve em data/ ou numa pasta protegida: " + mostrar(origem))
            res = _conferir_aberta(aberta, nome)
    except PathEscape:
        return recusa("ligação no caminho da origem do plugin: " + mostrar(origem))
    esperado = item.get("manifesto_sha256")
    if esperado and res["manifesto_sha256"] and esperado != res["manifesto_sha256"]:
        res["erros"].append({"campo": "manifesto_sha256", "motivo": "o plugin mudou desde o manifesto da ficha: prepare "
                             "a ficha de novo", "calculado": res["manifesto_sha256"]})
    return res
