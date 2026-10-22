#!/usr/bin/env python3
"""Atualiza uma fundação para o kit desta skill num só comando, com ensaio antes e registro depois (fluxo C6).

  checar   --raiz R                    só lê: versões, o que muda arquivo a arquivo, identidade e cadeia de eventos
  aplicar  --raiz R --backups PASTA    ensaia numa cópia e só então atualiza a raiz
  desfazer --registro ARQ.json         devolve o código anterior, se o banco não mudou de esquema

`aplicar`, em sequência, parando no primeiro problema (nada é escrito na raiz antes do passo 4):
  1. `checar`: recusa se algum arquivo de código foi ALTERADO LOCALMENTE desde a instalação (difere do kit
     novo e do hash registrado em registry/kit_install.json) — isso é decisão C6 à parte —, se houver nas áreas de
     código, ou no primeiro nível da raiz (módulo, pacote ou `.pth` que o uso normal importaria; segunda passada da
     revisão de segurança da 1.7.7, R177B-B-06; e a pasta `mcp/` mesmo sem `__init__`, que sem o SDK do MCP vira
     pacote de namespace; terceira passada, R177C-B-03), executável que nenhum dos dois conhece ou ligação, ou se
     faltar a identidade da administração ou a cadeia de eventos não conferir. O `checar` não executa nada da raiz: a
     cadeia é conferida pelo kit da skill, com o banco aberto somente leitura (auditoria Codex Security da 1.7.6, #8).
     Também recusa ligação ou vínculo físico onde a atualização grava (GRAVADOS; revisão de segurança da 1.7.7,
     R177-ATU-03);
  2. backup ANTES (código atual da raiz, rodado de uma cópia conferida por hash): `backup criar` + `backup
     verificar`, em PASTA/antes-kit-<versão>-<data>;
  3. ensaio: restaura essa cópia numa pasta temporária, aplica o kit novo (`instalar_kit.py --atualizar`), roda
     `init`, `eventos verificar` e a suíte de conformidade NELA. A suíte roda de cópias conferidas por hash (a do
     código da raiz antes, a da cópia atualizada depois), com os módulos enumerados da lista, nunca da árvore viva.
     Falha de teste que já acontecia antes da atualização é relatada, mas não bloqueia; falha nova (regressão)
     bloqueia;
  4. promoção na raiz: onde a atualização grava, conferido de novo (ligação ou vínculo físico criado durante o ensaio
     recusa; revisão de segurança da 1.7.7, segunda passada, R177B-B-05); `instalar_kit.py --atualizar` (guarda os
     arquivos substituídos), o `__pycache__` das áreas de código e do primeiro nível apagado sem seguir ligação
     (bytecode não conferido; R177-ATU-02, R177B-B-06), `init` e `eventos verificar`; depois, as instruções da raiz
     (AGENTS.md e CLAUDE.md, `instrucoes_raiz.py gerar`), sem bloquear. O instalador que para depois de gravar (saída
     sem `nada_escrito`) deixa a promoção interrompida: o `__pycache__` sai do mesmo jeito, e o registro é gravado e
     ancorado antes de parar, para o `desfazer` (terceira passada, R177C-B-04); a promoção que falhou e o próprio
     instalador desfez (código 5, `desfeito`, composição `nao_alterada`) conta como `nada_escrito`: para sem tocar a
     raiz (quarta passada, R177D-5);
  5. backup DEPOIS (código novo, com âncora) + `backup verificar`;
  6. registro em <raiz>/evidence/atualizacoes/, com a âncora, e resumo em linguagem simples; só então, sem bloquear
     e com tempo limite, o inventário do host (R177-VAL-04).
Do passo 4 em diante, o código que roda é o do kit da skill (o mesmo que acabou de ser conferido na raiz).
Com o kit da raiz já igual ao da skill, o `aplicar` só regenera as instruções da raiz se o texto que a skill geraria
for outro (skill nova com o mesmo kit), guardando as anteriores e com registro; sem diferença, não escreve nada.
`desfazer` devolve os arquivos substituídos (registry/kit_backup/...) e apaga os criados pela atualização (as
instruções da raiz também, salvo se editadas depois), só se o
`user_version` do banco não mudou; se mudou, a volta é restaurar a cópia ANTES numa pasta nova (C9). O registro só
vale com o SHA-256 que o `aplicar` anotou em registry/atualizacoes.jsonl, e cada caminho dele fica nas áreas de
código do kit (auditoria Codex Security da 1.7.6, #10). E só devolve se o código ainda é o que a atualização deixou
(`sha256_novo`): repetido, ou depois de outra atualização, recusa (revisão de segurança da 1.7.7). O registro, a
âncora e o `desfazer` moram em `registro_atualizacao.py`; a gravação sem seguir ligação, em `gravacao_segura.py`.
Os comandos que a saída sugere ao titular (voltar o código ou as instruções, conferir o host, gerar as instruções)
trazem o caminho completo do script e os caminhos entre aspas duplas: colados no PowerShell ou no bash, de qualquer
pasta, rodam como estão; caminho que não pode ir entre aspas com segurança não vira comando (`comando`).

Identidade: FUNDACAO_PRINCIPAL vem do lançador (administração da fundação); este script não a define.
Saída em JSON; códigos: 0 ok · 1 recusado ou falhou (com `etapa` e `motivo`) · 2 uso incorreto.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
if str(AQUI) not in sys.path:  # carregado por caminho (testes): o módulo vizinho também tem de ser achado
    sys.path.append(str(AQUI))
import codigo_conferido as conferido  # noqa: E402  (inventário, cópia conferida e execução isolada; #8)
import gravacao_segura as gravacao  # noqa: E402  (gravação sem seguir ligação nem vínculo físico; R177-ATU-03)
from registro_atualizacao import (GRAVADOS, Parada, agora, caminho_do_registro_valido, com_ligacao,  # noqa: E402
                                  desfazer, desvio, gravar, sha, user_version, versao_do_kit)  # registro e volta

KIT = AQUI.parent / "assets" / "fundacao-kit"
INSTALAR_KIT = AQUI / "instalar_kit.py"
INVENTARIAR_HOST = AQUI / "inventariar_host.py"
INVENTARIO_HOST = Path("registry") / "inventario-host.json"  # R54: skills, plugins, MCP e hooks do host
INSTRUCOES_RAIZ = AQUI / "instrucoes_raiz.py"  # AGENTS.md e CLAUDE.md gerados na raiz (proposta 1)
CONFIGURACAO = "registry"
IGNORAR = {"__pycache__", ".pytest_cache"}
VARIAVEL_IDENTIDADE = "FUNDACAO_" + "PRINCIPAL"
TEMPO = 3600
TEMPO_INVENTARIO = 120  # inventário do host: informativo, roda depois do registro (R177-VAL-04)
AREAS_DE_CODIGO = conferido.AREAS_DE_CODIGO  # fundacao/, templates/, tests/
RETIRADAS = "tests/testes_retirados.json"  # no kit novo: ID do teste retirado de propósito -> versão e motivo
NAO_LIBERADA = Path("state") / "restauracao-nao-liberada.json"  # marca do kit (backup.MARCA_NAO_LIBERADA)
# Dentro de aspas duplas, o PowerShell interpreta `$`, a crase e as aspas (também as tipográficas); o bash, `$`, a
# crase, as aspas, `!` (histórico) e a barra invertida antes delas ou dobrada (terceira passada).
NAO_CITAVEIS = frozenset('"$`!' + chr(0x201C) + chr(0x201D) + chr(0x201E))  # aspas, $, crase, ! e as tipográficas


def citar(caminho) -> str:
    """O caminho entre aspas duplas, que o PowerShell e o bash leem como um argumento só, com espaços e acentos.
    Recusa (ValueError) o que algum dos dois interpretaria dentro das aspas (NAO_CITAVEIS e caractere de controle), a
    barra invertida dobrada (o bash a reduz a uma) e a final (no bash ela escaparia a aspa de fechamento; no PowerShell
    5.1, a passagem para o programa também)."""
    texto = str(caminho)
    if any(c in NAO_CITAVEIS or c < " " for c in texto) or "\\\\" in texto or texto.endswith("\\"):
        raise ValueError("caminho com caractere que o PowerShell ou o bash interpretaria entre aspas: " + texto[:200])
    return '"' + texto + '"'


def comando(script: Path, *argumentos) -> str:
    """Comando pronto para o titular colar no PowerShell ou no bash, de qualquer pasta: `python`, o caminho completo do
    script e cada caminho (`Path`) entre aspas duplas; texto passa como está. Caminho que não pode ir entre aspas com
    segurança não vira comando: volta o aviso, e o caminho fica na saída para ser citado à mão (terceira passada)."""
    try:
        partes = ["python", citar(Path(script).resolve())]
        return " ".join(partes + [citar(a) if isinstance(a, Path) else str(a) for a in argumentos])
    except ValueError as exc:
        return "(comando não montado: " + str(exc) + "; cite-o à mão)"


def tupla(v: str | None) -> tuple:
    return tuple(int(x) if x.isdigit() else x for x in re.split(r"[.\-]", v or "0"))


def arquivos_do_kit(kit: Path = KIT) -> dict[str, str]:
    """Código e modelos do kit (fora de registry/, que é configuração local): caminho -> sha256."""
    out = {}
    for p in sorted(kit.rglob("*")):
        rel = p.relative_to(kit)
        if p.is_file() and not set(rel.parts) & IGNORAR and p.suffix not in (".pyc", ".sqlite") \
                and rel.parts[0] != CONFIGURACAO:
            out[rel.as_posix()] = sha(p)
    return out


def hashes_instalados(raiz: Path) -> dict[str, str]:
    """Último hash que o `instalar_kit.py` registrou para cada arquivo (copiado ou substituído)."""
    arq = Path(raiz) / "registry" / "kit_install.json"
    conhecidos: dict[str, str] = {}
    try:
        historico = json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):  # ilegível ou trocado (R177C-B-04): o `checar` recusa o que difere
        return conhecidos
    for reg in historico if isinstance(historico, list) else []:
        if not isinstance(reg, dict):
            continue
        for chave, campo in (("copiados", "sha256"), ("identicos_registrados", "sha256"),
                             ("substituidos", "sha256_novo")):
            for item in reg.get(chave) or []:
                if isinstance(item, dict) and item.get("path") and item.get(campo):
                    conhecidos[item["path"]] = item[campo]
        for item in reg.get("orfaos_retirados") or []:  # já guardados no backup por uma atualização
            if isinstance(item, dict):
                conhecidos.pop(item.get("path"), None)
    return conhecidos


def retiradas_declaradas(kit: Path = KIT) -> dict:
    """Testes que o kit novo retirou de propósito (`tests/testes_retirados.json`): ID -> versão e motivo."""
    arq = Path(kit) / RETIRADAS
    try:
        dados = json.loads(arq.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        raise Parada("checar", "a declaração de testes retirados do kit não é JSON válido", erro=str(exc))
    if not isinstance(dados, dict) or not all(isinstance(v, dict) and str(v.get("motivo", "")).strip()
                                              for v in dados.values()):
        raise Parada("checar", "a declaração de testes retirados precisa de ID -> {versao, motivo}")
    return dados


def ambiente() -> dict:
    return {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}


def rodar(cmd: list, cwd: Path, timeout: int = TEMPO) -> tuple:
    """(código, JSON da saída ou None, fim do stderr)."""
    r = subprocess.run([str(c) for c in cmd], cwd=str(cwd), env=ambiente(), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    texto = (r.stdout or "").strip()
    dados = None
    for inicio in (0, texto.rfind("\n{") + 1):
        try:
            dados = json.loads(texto[inicio:])
            break
        except ValueError:
            continue
    return r.returncode, dados, (r.stderr or "")[-2000:]


def fundacao(codigo: Path, raiz: Path, *args: str) -> tuple:
    """CLI do kit sobre a `raiz`, rodando o código de `codigo`: o kit da skill ou uma cópia conferida do código da
    raiz, nunca a árvore viva dela (auditoria Codex Security da 1.7.6, #8)."""
    return rodar(conferido.python_isolado(codigo, conferido.CLI, "--raiz", raiz, *args), cwd=raiz)


def suite(origem: Path, arquivos: dict, padrao: str, copia: Path) -> dict:
    """Suíte de conformidade numa cópia conferida de `origem` (só os `arquivos`, caminho -> sha256, e registry/, que
    os testes do kit copiam, sem as cópias do código guardadas pela promoção; R177-ATU-01), com os módulos enumerados
    da lista: total, ids das falhas e pulados."""
    try:
        conferido.preparar_copia(origem, arquivos, copia, dados=(CONFIGURACAO,))
    except (ValueError, OSError) as exc:
        raise Parada("ensaio", "a cópia dos testes não conferiu com a lista (" + str(exc)[:300] + "): algo mudou nas "
                     "áreas de código depois do `checar`; a raiz NÃO foi alterada")
    modulos = conferido.modulos_de_teste(arquivos, padrao)
    _code, dados, erro = rodar(conferido.python_isolado(copia, conferido.RUNNER, json.dumps(modulos)), cwd=copia)
    if not isinstance(dados, dict):
        return {"total": 0, "falhas": ["suite-nao-rodou: " + erro[-300:]], "pulados": 0}
    return dados


def cadeia_de_eventos(raiz: Path) -> tuple:
    """(íntegra?, detalhes) da cadeia de eventos da raiz, recalculada pelo kit da skill com o banco aberto somente
    leitura: nada da raiz é importado e nada é escrito (#8). `eventos verificar` sai com código 0 mesmo com a cadeia
    quebrada; por isso vale `cadeia_integra`, não o código de saída."""
    code, dados, erro = rodar(conferido.python_isolado(KIT, conferido.CADEIA, raiz), cwd=KIT)
    if code != 0 or not isinstance(dados, dict):
        return False, {"erro": erro[-300:]}
    return dados.get("cadeia_integra") is True, dados


def rota_sigilosa(raiz: Path) -> dict:
    """Desvio da rota sigilosa da raiz julgado pelo kit NOVO (avaliação E11, F-05): sem aceite assinado do titular sobre
    a política exata, o kit o deixa sem efeito ao carregar (vale a rota distribuída). Não bloqueia: vai aos avisos."""
    codigo = ("import json\nfrom fundacao.core.politica_rotas import desvio_sem_decisao\n"
              "print(json.dumps({'desvio_sem_decisao': desvio_sem_decisao(sys.argv[1])}, ensure_ascii=False))")
    code, dados, erro = rodar(conferido.python_isolado(KIT, codigo, raiz), cwd=KIT)
    if code != 0 or not isinstance(dados, dict):
        return {"conferida": False, "erro": erro[-300:]}
    return {"conferida": True, **dados}


def checar(raiz: Path) -> dict:
    """Só lê. `pode_aplicar` e os `motivos` de recusa, com o que muda arquivo a arquivo; `avisos` não bloqueiam."""
    return _inspecionar(raiz)[0]


def _inspecionar(raiz: Path) -> tuple:
    """O `checar` e o inventário conferido das áreas de código (caminho -> sha256), que o `aplicar` usa para montar
    as cópias de onde o código antigo e os testes rodam. Nada da raiz é executado aqui (#8)."""
    raiz = Path(raiz).resolve()
    res = {"raiz": str(raiz), "kit_na_raiz": versao_do_kit(raiz), "kit_da_skill": versao_do_kit(KIT), "motivos": []}
    if res["kit_na_raiz"] is None or not (raiz / "state" / "state.sqlite").is_file():
        res["motivos"].append("a pasta não é uma fundação instalada pelo kit (fundacao/__init__.py e state/state.sqlite)")
        res["pode_aplicar"] = False
        return res, {}
    if tupla(res["kit_da_skill"]) < tupla(res["kit_na_raiz"]):
        res["motivos"].append("o kit desta skill é mais antigo que o da raiz: atualize a skill antes")
    conhecidos = hashes_instalados(raiz)
    mudancas = {"copiar": [], "atualizar": [], "identicos": 0, "alterados_localmente": [], "retirar": []}
    do_kit = arquivos_do_kit()
    mudancas["por_ligacao"] = []
    for rel, novo in do_kit.items():
        alvo = raiz / rel
        if com_ligacao(raiz, rel):
            mudancas["por_ligacao"].append(rel)
            continue
        if not alvo.exists():
            mudancas["copiar"].append(rel)
        elif not alvo.is_file():
            mudancas["alterados_localmente"].append({"path": rel, "motivo": "no destino não é arquivo"})
        else:
            atual = sha(alvo)
            if atual == novo:
                mudancas["identicos"] += 1
            elif conhecidos.get(rel) == atual:
                mudancas["atualizar"].append(rel)
            else:
                motivo = ("difere do kit novo e do hash registrado na instalação" if rel in conhecidos
                          else "sem hash de instalação registrado")
                mudancas["alterados_localmente"].append({"path": rel, "motivo": motivo})
    # Inventário exato das áreas de código (#8) e do primeiro nível da raiz (R177B-B-06): todo executável conferido pelo
    # hash do kit novo ou pelo registrado na instalação; o que nenhum dos dois conhece, o que difere do hash conhecido
    # e as ligações recusam.
    vistos = conferido.inventario(raiz, do_kit, conhecidos)
    mudancas["executaveis_a_mais"] = vistos["a_mais"]
    mudancas["bytecode_a_apagar"] = conferido.bytecode(raiz)  # não recusa: a promoção o apaga (R177-ATU-02, B-06)
    # Órfãos: o kit anterior instalou, o novo não tem mais (o instalar_kit.py os guarda no backup).
    mudancas["entradas_invalidas"] = sorted(rel for rel in conhecidos if not caminho_do_registro_valido(rel))
    candidatos = [rel for rel in conhecidos if rel not in do_kit and caminho_do_registro_valido(rel)
                  and rel.split("/", 1)[0] in AREAS_DE_CODIGO and (raiz / rel).is_file()]
    mudancas["alterados_localmente"] += [{"path": rel, "motivo": "o kit novo não tem mais e difere do hash registrado "
                                          "na instalação"} for rel in candidatos if rel in vistos["alterados"]]
    mudancas["por_ligacao"] = sorted(set(mudancas["por_ligacao"]) | set(vistos["ligacoes"])
                                     | {rel for rel in candidatos if com_ligacao(raiz, rel)})
    mudancas["retirar"] = sorted(rel for rel in candidatos if not com_ligacao(raiz, rel)
                                 and rel not in vistos["alterados"])
    res["mudancas"] = mudancas
    if mudancas["por_ligacao"]:
        res["motivos"].append("ligação ou junção nas áreas de código, no primeiro nível da raiz (com nome de módulo, "
                              "de pacote ou __pycache__) ou no caminho de um arquivo do kit ("
                              + ", ".join(mudancas["por_ligacao"][:5]) + "): a atualização escreveria, retiraria ou "
                              "executaria o que está do outro lado; investigue antes de atualizar")
    mudancas["gravacao_desviada"] = gravacao.desviados(raiz, GRAVADOS)
    if mudancas["gravacao_desviada"]:
        res["motivos"].append(desvio(mudancas["gravacao_desviada"], "a atualização"))
    if mudancas["entradas_invalidas"]:
        res["motivos"].append("registry/kit_install.json tem caminho que o instalador nunca grava (com `..`, absoluto "
                              "ou com barra invertida): o registro pode ter sido adulterado; investigue antes de "
                              "atualizar")
    if mudancas["alterados_localmente"]:
        res["motivos"].append("há arquivo de código alterado localmente desde a instalação: a atualização o "
                              "substituiria; revise-o antes (fluxo C6)")
    if mudancas["executaveis_a_mais"]:
        res["motivos"].append("há arquivo executável nas áreas de código (fundacao/, templates/, tests/) ou no "
                              "primeiro nível da raiz que nem o kit novo nem o registro da instalação conhecem ("
                              + ", ".join(mudancas["executaveis_a_mais"][:5]) + "): a atualização o executaria, ou o "
                              "uso normal (`python -m fundacao` na raiz, que a põe no caminho de importação) o "
                              "importaria no lugar do módulo de mesmo nome, também de dentro de uma pasta com o nome "
                              "de um pacote que o kit importa de fora da biblioteca padrão ("
                              + ", ".join(n + "/" for n in conferido.IMPORTADOS_DE_FORA) + ", mesmo sem __init__); "
                              "retire-o ou mova-o para fora dessas pastas (ou para uma subpasta que não seja pacote "
                              "nem tenha um desses nomes) e repita (fluxo C6)")
    if (raiz / NAO_LIBERADA).exists():
        res["motivos"].append("raiz de restauração não liberada (" + NAO_LIBERADA.as_posix() + "): não use; refaça a "
                              "restauração numa pasta nova (fluxo C9)")
    res["identidade"] = os.environ.get(VARIAVEL_IDENTIDADE) or None
    if not res["identidade"]:
        res["motivos"].append("identidade ausente: " + VARIAVEL_IDENTIDADE + " vem do lançador (administração da fundação)")
    integra, res["cadeia_de_eventos"] = cadeia_de_eventos(raiz)
    if not integra:
        res["motivos"].append("a cadeia de eventos da raiz não confere: investigue antes de atualizar")
    res["user_version"] = user_version(raiz)
    res["instrucoes_raiz"] = _plano_instrucoes(raiz)
    res["rota_sigilosa"] = rota_sigilosa(raiz)
    res["avisos"] = (["rota sigilosa: " + res["rota_sigilosa"]["desvio_sem_decisao"]]
                     if res["rota_sigilosa"].get("desvio_sem_decisao") else [])
    res["nada_a_fazer"] = not (mudancas["copiar"] or mudancas["atualizar"] or mudancas["alterados_localmente"]
                               or mudancas["retirar"])
    res["pode_aplicar"] = not res["motivos"]
    return res, vistos["conferidos"]


def _codigo_conferido(raiz: Path, conferidos: dict, destino: Path) -> Path:
    """Cópia conferida do pacote `fundacao/` da raiz (o código ANTES), de onde rodam o backup ANTES e a restauração do
    ensaio: o que roda é exatamente o que o `checar` conferiu, mesmo que a raiz mude depois (#8)."""
    try:
        conferido.preparar_copia(raiz, {rel: h for rel, h in conferidos.items() if rel.startswith("fundacao/")},
                                 destino, areas=("fundacao",))
    except (ValueError, OSError) as exc:
        raise Parada("backup", "o código da raiz mudou depois do `checar` (" + str(exc)[:300] + "): nada foi "
                     "executado nem alterado; confira e repita")
    return destino


def _backup(codigo: Path, raiz: Path, destino: Path, rotulo: str) -> dict:
    """`backup criar` + `backup verificar` com o código de `codigo` (cópia conferida do código da raiz ANTES; o kit da
    skill DEPOIS); a âncora vem do kit ou é calculada aqui."""
    code, dados, erro = fundacao(codigo, raiz, "backup", "criar", "--destino", str(destino), "--rotulo", rotulo)
    if code != 0 or not isinstance(dados, dict):
        raise Parada("backup", "`backup criar` falhou (" + rotulo + ")", erro=erro, saida=dados)
    ancora = dados.get("sha256_manifesto") or sha(destino / "manifest.json")
    extra = ["--sha256-manifesto", ancora] if dados.get("sha256_manifesto") else []
    code, ver, erro = fundacao(codigo, raiz, "backup", "verificar", "--origem", str(destino), *extra)
    if code != 0 or not (isinstance(ver, dict) and ver.get("ok")):
        raise Parada("backup", "a cópia " + rotulo + " não conferiu", erro=erro, verificacao=ver)
    return {"pasta": str(destino), "rotulo": rotulo, "sha256_manifesto": ancora,
            "ancora_pelo_kit": bool(dados.get("sha256_manifesto")), "arquivos": len(dados.get("files", []))}


def _conferir_antes_da_promocao(raiz: Path) -> None:
    """Onde a atualização grava, conferido de novo logo antes da promoção: o `checar` rodou antes do ensaio inteiro, e
    vínculo físico ou ligação criados nesse intervalo levariam o registro da instalação, as cópias ou a âncora para
    fora da raiz (R177B-B-05). Até aqui nada foi escrito na raiz."""
    desviados = gravacao.desviados(raiz, GRAVADOS)
    if desviados:
        raise Parada("promocao", desvio(desviados, "a atualização") + "; apareceu depois do `checar`, durante o "
                     "ensaio: a raiz NÃO foi alterada")


def _instalar_kit(destino: Path) -> dict:
    code, dados, erro = rodar([sys.executable, "-B", str(INSTALAR_KIT), "--destino", str(destino), "--atualizar"],
                              cwd=AQUI)
    if code != 0 or not isinstance(dados, dict) or dados.get("composicao") != "verificada":
        raise Parada("instalar_kit", "o kit não ficou verificado em " + str(destino), codigo=code, saida=dados,
                     erro=erro)
    return dados


def _promover(raiz: Path, registro: dict) -> dict:
    """`instalar_kit.py --atualizar` na raiz e, depois, o `__pycache__` das áreas de código e do primeiro nível
    apagado sem seguir ligação: bytecode não conferido rodaria no uso normal no lugar da fonte (R177-ATU-02,
    R177B-B-06). O instalador que parava depois de gravar (código 3 com o registro da instalação não gravado ou a
    composição divergente; 5 com a promoção que falhou) deixava a raiz no kit novo sem registro ancorado, e o
    `desfazer` recusava. Agora, sem `nada_escrito` na saída dele, a promoção entra no registro marcada como
    interrompida, com a saída (o plano que o `desfazer` devolve), e o bytecode sai do mesmo jeito; o `aplicar` grava e
    ancora o registro antes de parar. Com `nada_escrito`, para como antes; sem saída legível não há plano, e a volta é
    a cópia ANTES (C9) (terceira passada, R177C-B-04). A promoção que falhou e o próprio instalador desfez (código 5,
    `desfeito`, composição `nao_alterada`; no Windows, por exemplo, arquivo preso pelo antivírus) deixa o código da
    raiz como estava: conta como `nada_escrito`, sem âncora nem `__pycache__` apagado, e a mensagem diz que a raiz não
    foi alterada; antes ia para o registro ancorado, e o `desfazer` recusava e mandava à cópia ANTES (quarta passada,
    R177D-5). São as duas únicas saídas do instalador sem nada mudado nas áreas de código."""
    try:
        registro["promocao"] = {"instalar_kit": _instalar_kit(raiz)}
    except Parada as p:
        saida, codigo = p.detalhes.get("saida"), p.detalhes.get("codigo")
        if isinstance(saida, dict) and saida.get("nada_escrito") is True:
            raise  # nada foi gravado na raiz
        if isinstance(saida, dict) and saida.get("desfeito") is True and saida.get("composicao") == "nao_alterada":
            raise Parada("instalar_kit", "a promoção falhou, e o próprio instalador a desfez (código " + str(codigo)
                         + "): o código da raiz continua o de antes e NÃO foi alterado; veja `erros` na saída do "
                         "instalador (por exemplo, arquivo preso pelo antivírus), resolva e repita o `aplicar`",
                         **p.detalhes) from None  # como com `nada_escrito`: sem âncora nem `__pycache__` apagado
        apagado, nao_apagado = conferido.apagar_bytecode(raiz)  # a raiz pode ter ficado com o código novo
        if not isinstance(saida, dict):  # sem a saída do instalador, não há plano para o `desfazer`
            raise Parada("instalar_kit", "o instalador parou sem saída legível (código " + str(codigo) + "): a raiz "
                         "pode ter sido alterada; confira e, para voltar, restaure a cópia ANTES numa pasta nova (C9)",
                         bytecode_apagado=apagado, bytecode_nao_apagado=nao_apagado, **p.detalhes) from None
        motivo = ("o instalador parou depois de gravar na raiz (código " + str(codigo) + ", composição "
                  + str(saida.get("composicao")) + "): a promoção ficou interrompida, e a raiz pode estar no kit "
                  "novo, sem `init`; o `desfazer` com o registro desta atualização devolve o código anterior")
        registro["promocao"] = {"instalar_kit": saida, "interrompida": motivo, "bytecode_apagado": apagado,
                                "bytecode_nao_apagado": nao_apagado}
        raise Parada("instalar_kit", motivo, **p.detalhes) from None
    promo = registro["promocao"]
    promo["bytecode_apagado"], promo["bytecode_nao_apagado"] = conferido.apagar_bytecode(raiz)
    return promo


def _init_e_cadeia(raiz: Path, etapa: str) -> dict:
    """`init` e `eventos verificar` com o kit da skill (o mesmo código que a raiz ou a cópia acabou de receber)."""
    code, init, erro = fundacao(KIT, raiz, "init")
    if code != 0:
        raise Parada(etapa, "`init` falhou", erro=erro, saida=init)
    code, cadeia, erro = fundacao(KIT, raiz, "eventos", "verificar")
    if code != 0 or not (isinstance(cadeia, dict) and cadeia.get("cadeia_integra") is True):
        raise Parada(etapa, "a cadeia de eventos não conferiu depois do `init`", erro=erro, saida=cadeia)
    return {"init": init, "cadeia_de_eventos": cadeia}


def _ensaio(raiz: Path, codigo: Path, conferidos: dict, antes: dict, padrao: str, manter: bool = False) -> dict:
    """Restaura a cópia ANTES numa pasta temporária e aplica nela o kit novo, com `init`, cadeia e suíte.
    Regressão = teste que falha na cópia atualizada e não falhava antes, ou que passava e na cópia
    sumiu ou passou a ser pulado sem a retirada declarada pelo kit novo (catraca, proposta 5). A suíte de antes roda
    de uma cópia conferida do código da raiz e a de depois, de uma cópia conferida da cópia atualizada (#8). As
    cópias têm os dados da fundação: são apagadas no fim, também na falha (o registro guarda o motivo de cada
    teste), salvo com `manter`."""
    tmp = Path(tempfile.mkdtemp(prefix="ensaio-atualizacao-"))
    try:
        base = suite(raiz, conferidos, padrao, tmp / "testes-antes")
        return _ensaio_na_copia(raiz, codigo, antes, padrao, base, tmp)
    except Parada as p:
        if not manter:
            p.detalhes["copia_de_ensaio"] = None
            p.detalhes["copia_apagada"] = "use --manter-ensaio para examiná-la"
        raise
    finally:
        if not manter:
            shutil.rmtree(tmp, ignore_errors=True)


def _ensaio_na_copia(raiz: Path, codigo: Path, antes: dict, padrao: str, base: dict, tmp: Path) -> dict:
    copia = tmp / "raiz"
    extra = ["--sha256-manifesto", antes["sha256_manifesto"]] if antes["ancora_pelo_kit"] else []
    code, rest, erro = fundacao(codigo, raiz, "backup", "restaurar", "--origem", antes["pasta"], "--destino",
                                str(copia), "--retiradas", str(raiz / "state" / "retiradas.jsonl"), *extra)
    if code != 0 or not (isinstance(rest, dict) and rest.get("released")):
        raise Parada("ensaio", "a cópia ANTES não restaurou numa pasta de ensaio", erro=erro, saida=rest,
                     copia_de_ensaio=str(copia))
    kit = _instalar_kit(copia)
    conferencia = _init_e_cadeia(copia, "ensaio")
    depois = suite(copia, arquivos_do_kit(), padrao, tmp / "testes-depois")
    regressoes = sorted(set(depois["falhas"]) - set(base["falhas"]))
    declaradas = retiradas_declaradas()
    passavam = set(base.get("ids", [])) - set(base["falhas"]) - set(base.get("pulados_ids", {}))
    sumidos = sorted(set(base.get("ids", [])) - set(depois.get("ids", [])) - set(declaradas))
    pulados_novos = sorted((passavam & set(depois.get("pulados_ids", {}))) - set(declaradas))
    ensaio = {"suite_antes_na_raiz": base, "suite_na_copia_atualizada": depois, "regressoes": regressoes,
              "copias_conferidas": True,  # as duas suítes rodaram de cópias conferidas por hash (#8)
              "testes_sumidos": sumidos, "pulados_novos": pulados_novos,
              "retiradas_declaradas": sorted(set(declaradas) & set(base.get("ids", []))),
              "falhas_que_ja_existiam": sorted(set(depois["falhas"]) & set(base["falhas"])),
              "kit": {"substituidos": len(kit.get("substituidos", [])), "copiados": len(kit.get("copiados", [])),
                      "orfaos_retirados": len(kit.get("orfaos_retirados", []))},
              "user_version_na_copia": (conferencia["init"] or {}).get("user_version")}
    if regressoes or sumidos or pulados_novos:
        raise Parada("ensaio", "a atualização quebra, apaga ou passa a pular testes que passavam antes (sem a "
                     "retirada declarada em " + RETIRADAS + " do kit novo); a raiz NÃO foi alterada",
                     regressoes=regressoes, testes_sumidos=sumidos, pulados_novos=pulados_novos,
                     ensaio=ensaio, copia_de_ensaio=str(copia))
    return ensaio


def _inventario_host(raiz: Path) -> dict | None:
    """Confere o inventário do ecossistema do host (proposta 15), se a fundação tiver um. Não bloqueia: mudança
    no host é informação para o titular conferir e regravar, não falha da atualização do kit. Roda depois do registro,
    com TEMPO_INVENTARIO: travar ou falhar vira `conferido: False` com o motivo, nunca exceção (R177-VAL-04)."""
    arq, erro = raiz / INVENTARIO_HOST, ""
    if not arq.is_file():
        return None
    try:
        _code, dados, erro = rodar([sys.executable, "-B", str(INVENTARIAR_HOST), "verificar", "--inventario",
                                    str(arq), "--raiz", str(raiz)], cwd=AQUI, timeout=TEMPO_INVENTARIO)
        mudancas = {cat: {k: len(v) for k, v in d.items() if v} for cat, d in dados["diferencas"].items()}
    except subprocess.TimeoutExpired:
        return {"conferido": False, "motivo": "tempo esgotado: " + str(TEMPO_INVENTARIO) + " s"}
    except Exception as exc:  # noqa: BLE001 — informativo: nada aqui derruba a atualização já registrada
        return {"conferido": False, "motivo": "saída inesperada (" + type(exc).__name__ + ") " + (erro or "")[-200:]}
    return {"conferido": True, "sem_mudancas": bool(dados.get("ok")),
            "mudancas": {cat: m for cat, m in mudancas.items() if m}}


def _resumo_host(raiz: Path, host: dict | None) -> list:
    if not host:
        return []
    if not host.get("conferido"):
        return ["Inventário do host não conferido (" + str(host.get("motivo"))[:200] + "); a atualização já está "
                "registrada. Confira depois: "
                + comando(INVENTARIAR_HOST, "verificar", "--inventario", raiz / INVENTARIO_HOST, "--raiz", raiz)]
    return ["Ecossistema do host (skills, plugins, MCP, hooks): " + (
        "igual ao inventário." if host["sem_mudancas"] else "mudou desde o inventário: "
        + json.dumps(host["mudancas"], ensure_ascii=False) + " — confira e regrave com: "
        + comando(INVENTARIAR_HOST, "gravar", "--saida", raiz / INVENTARIO_HOST, "--raiz", raiz, "--substituir"))]


def _plano_instrucoes(raiz: Path) -> dict:
    """Só lê (`instrucoes_raiz.py gerar --simular`): o que mudaria no AGENTS.md e no CLAUDE.md da raiz."""
    _code, dados, erro = rodar([sys.executable, "-B", str(INSTRUCOES_RAIZ), "gerar", "--raiz", str(raiz), "--simular"],
                               cwd=AQUI)
    if not isinstance(dados, dict):
        return {"erro": (erro or "")[-300:]}
    if not dados.get("ok"):  # escrito à mão (conflito) ou ligação no lugar do arquivo (erro; R177-ATU-03)
        return {"conflito": dados["conflito"]} if dados.get("conflito") else {"erro": str(dados.get("erro"))[:300]}
    return {"AGENTS.md": dados["agents"]["acao"], "CLAUDE.md": dados["claude"]["acao"]}


def _instrucoes_raiz(raiz: Path, carimbo: str) -> dict:
    """Regenera o AGENTS.md e o CLAUDE.md da raiz (proposta 1), guardando antes os que já existiam, para o
    `desfazer`, numa pasta nova de registry/kit_backup/, sem ligação no caminho e com arquivos criados com
    exclusividade (R177-ATU-03). Não bloqueia: AGENTS.md escrito à mão fica como está e o resumo pede a decisão do
    titular."""
    plano = _plano_instrucoes(raiz)
    if "erro" in plano or "conflito" in plano:
        return {"gerado": False, **plano}
    rel = "registry/kit_backup/instrucoes-" + carimbo
    guarda, guardados = raiz / rel, []
    try:
        for nome, acao in plano.items():
            if acao == "atualizar":
                if not guardados:
                    gravacao.pasta_nova(raiz, rel)
                dados = (raiz / nome).read_bytes()
                gravacao.criar(guarda / nome, dados)
                guardados.append({"path": nome, "sha256_anterior": hashlib.sha256(dados).hexdigest()})
    except OSError as exc:
        return {"gerado": False, "erro": "a versão anterior não foi guardada: " + str(exc)}
    code, dados, erro = rodar([sys.executable, "-B", str(INSTRUCOES_RAIZ), "gerar", "--raiz", str(raiz)], cwd=AQUI)
    res = {"gerado": code == 0 and isinstance(dados, dict) and bool(dados.get("ok")), "acoes": plano,
           "copia": str(guarda) if guardados else None, "guardados": guardados}
    if res["gerado"]:
        res["sha256"] = {"AGENTS.md": dados["agents"]["sha256"], "CLAUDE.md": dados["claude"]["sha256"]}
    else:
        res["erro"] = (erro or "")[-300:]
    return res


def _resumo_instrucoes(raiz: Path, instr: dict) -> list:
    if instr.get("gerado"):
        mudou = [nome for nome, acao in instr["acoes"].items() if acao != "igual"]
        return (["Instruções da raiz geradas pela skill (" + ", ".join(mudou) + "): as sessões abertas nesta pasta "
                 "passam a lê-las ao iniciar."] if mudou else [])
    if instr.get("conflito"):
        return ["O AGENTS.md da raiz foi escrito à mão e não foi alterado. Revise-o e, para a skill passar a "
                "mantê-lo (o seu texto fica no trecho do titular), rode: "
                + comando(INSTRUCOES_RAIZ, "gerar", "--raiz", raiz, "--adotar")]
    return ["Atenção: as instruções da raiz não foram geradas (" + str(instr.get("erro"))[:200] + "); "
            "rode depois: " + comando(INSTRUCOES_RAIZ, "gerar", "--raiz", raiz)]


def _so_instrucoes(raiz: Path, pre: dict, carimbo: str) -> dict:
    """Kit igual: nada a fazer no código. Se o texto que `instrucoes_raiz.py gerar` produziria difere do atual (skill
    nova com o mesmo kit), as instruções da raiz são regeneradas pelas regras dele (AGENTS.md escrito à mão, sem a
    marca da skill, não é tocado), com as anteriores guardadas e registro ancorado, que o `desfazer` aceita.
    Sem diferença, nada é escrito (defeito anotado na liberação da 1.7.6: o AGENTS.md ficava com o texto anterior)."""
    nada = ["A fundação já está no kit " + str(pre["kit_na_raiz"]) + ": nada a fazer."]
    plano = pre["instrucoes_raiz"]
    if "AGENTS.md" in plano and set(plano.values()) == {"igual"}:
        return {"ok": True, "nada_a_fazer": True, "checar": pre, "resumo": nada}
    instr = _instrucoes_raiz(raiz, carimbo) if "AGENTS.md" in plano else {"gerado": False, **plano}
    if not instr.get("gerado") and ("conflito" in instr or "AGENTS.md" not in plano):  # nada foi escrito
        return {"ok": True, "nada_a_fazer": True, "checar": pre, "resumo": nada + _resumo_instrucoes(raiz, instr)}
    registro = {"schema_version": "fundacao.atualizacao/1", "raiz": str(raiz), "iniciado_em": carimbo,
                "kit_antes": pre["kit_na_raiz"], "kit_da_skill": pre["kit_da_skill"], "identidade": pre["identidade"],
                "user_version_antes": pre["user_version"], "so_instrucoes": True, "instrucoes_raiz": instr,
                "concluido_em": agora()}
    arq = gravar(raiz, "instrucoes-raiz-" + carimbo + ".json", registro, ancorar=bool(instr.get("gerado")))
    resumo = ["A fundação já está no kit " + str(pre["kit_na_raiz"]) + ": o código não muda."]
    resumo += _resumo_instrucoes(raiz, instr) + ["Registro: " + str(arq) + "."]
    if instr.get("gerado"):
        if instr.get("copia"):
            resumo.append("As versões anteriores ficaram em " + instr["copia"] + ".")
        resumo.append("Para voltar as instruções: " + comando(Path(__file__), "desfazer", "--registro", arq))
    return {"ok": True, "nada_a_fazer": False, "so_instrucoes": True, "registro": str(arq), "resumo": resumo}


def aplicar(raiz: Path, backups: Path, padrao: str, manter_ensaio: bool = False) -> dict:
    raiz, backups = Path(raiz).resolve(), Path(backups).resolve()
    carimbo = agora()
    pre, conferidos = _inspecionar(raiz)
    if not pre["pode_aplicar"]:
        raise Parada("checar", "; ".join(pre["motivos"]), checar=pre)
    if pre["nada_a_fazer"]:
        return _so_instrucoes(raiz, pre, carimbo)
    nova, antiga = pre["kit_da_skill"], pre["kit_na_raiz"]
    registro = {"schema_version": "fundacao.atualizacao/1", "raiz": str(raiz), "iniciado_em": carimbo,
                "kit_antes": antiga, "kit_da_skill": nova, "identidade": pre["identidade"],
                "mudancas": pre["mudancas"], "user_version_antes": pre["user_version"]}
    codigo = Path(tempfile.mkdtemp(prefix="codigo-conferido-"))
    try:
        antes = _codigo_conferido(raiz, conferidos, codigo / "antes")  # o código ANTES roda só desta cópia
        rotulo = "antes-kit-" + nova + "-" + carimbo
        registro["antes"] = _backup(antes, raiz, backups / rotulo, rotulo)
        registro["ensaio"] = _ensaio(raiz, antes, conferidos, registro["antes"], padrao, manter_ensaio)
        _conferir_antes_da_promocao(raiz)
        promo = _promover(raiz, registro)  # instalador e `__pycache__` (R177-ATU-02); interrompida: R177C-B-04
        promo.update(_init_e_cadeia(raiz, "promocao"))
        registro["user_version_depois"] = user_version(raiz)
        registro["instrucoes_raiz"] = _instrucoes_raiz(raiz, carimbo)  # antes da cópia DEPOIS, que as leva
        rotulo = "depois-kit-" + nova + "-" + carimbo
        registro["depois"] = _backup(KIT, raiz, backups / rotulo, rotulo)
    except Parada as p:
        registro["falha"] = {"etapa": p.etapa, "motivo": p.motivo, **p.detalhes}
        nome = "falha-atualizacao-kit-" + nova + "-" + carimbo + ".json"
        try:  # falha depois da promoção deixa a raiz no kit novo: o `desfazer` precisa poder usar este registro
            p.detalhes["registro"] = str(gravar(raiz, nome, registro, ancorar="promocao" in registro))
        except Parada as q:
            p.detalhes["registro"], p.detalhes["registro_nao_gravado"] = None, q.motivo
        else:
            if "promocao" in registro:  # registro ancorado: o comando pronto para voltar o código (R177C-B-04)
                p.detalhes["para_voltar"] = comando(Path(__file__), "desfazer", "--registro",
                                                    Path(p.detalhes["registro"]))
        raise
    finally:
        shutil.rmtree(codigo, ignore_errors=True)
    registro["kit_depois"] = versao_do_kit(raiz)
    registro["concluido_em"] = agora()
    try:  # registro e âncora ANTES do inventário do host: travar ou falhar nele não perde a atualização (R177-VAL-04)
        arq = gravar(raiz, "atualizacao-kit-" + nova + "-" + carimbo + ".json", registro, ancorar=True)
    except Parada as p:
        raise Parada("registro", "a fundação foi atualizada, mas " + p.motivo + "; sem registro não há `desfazer`: a "
                     "volta é a cópia ANTES numa pasta nova (C9)", copia_antes=registro["antes"]["pasta"])
    host = _inventario_host(raiz)
    ensaio = registro["ensaio"]
    resumo = ["Fundação atualizada do kit " + str(antiga) + " para " + str(registro["kit_depois"]) + ".",
              "Cópia de segurança ANTES: " + registro["antes"]["pasta"] + " (âncora "
              + registro["antes"]["sha256_manifesto"][:12] + "...).",
              "Ensaio numa cópia restaurada: " + str(ensaio["suite_na_copia_atualizada"]["total"])
              + " testes, nenhuma regressão.",
              "Cópia de segurança DEPOIS: " + registro["depois"]["pasta"] + " (âncora "
              + registro["depois"]["sha256_manifesto"][:12] + "...).",
              "Registro: " + str(arq) + "."]
    if ensaio["falhas_que_ja_existiam"]:
        resumo.append("Atenção: " + str(len(ensaio["falhas_que_ja_existiam"])) + " teste(s) já falhava(m) antes e "
                      "continua(m) falhando (não é regressão): " + ", ".join(ensaio["falhas_que_ja_existiam"][:3]))
    if registro["promocao"]["bytecode_nao_apagado"]:
        resumo.append("Atenção: o bytecode destas pastas não foi apagado; apague-as antes de usar a fundação (o Python "
                      "as refaz da fonte): " + "; ".join(registro["promocao"]["bytecode_nao_apagado"][:3]))
    resumo += _resumo_instrucoes(raiz, registro["instrucoes_raiz"]) + _resumo_host(raiz, host)
    resumo.append("Para voltar o código: " + comando(Path(__file__), "desfazer", "--registro", arq))
    return {"ok": True, "registro": str(arq), "inventario_host": host, "resumo": resumo}


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("checar")
    c.add_argument("--raiz", type=Path, required=True)
    a = sub.add_parser("aplicar")
    a.add_argument("--raiz", type=Path, required=True)
    a.add_argument("--backups", type=Path, required=True,
                   help="pasta das cópias ANTES e DEPOIS (de preferência em outro disco)")
    a.add_argument("--padrao-testes", default="test*.py", help="padrão da suíte de conformidade no ensaio")
    a.add_argument("--manter-ensaio", action="store_true",
                   help="não apaga a cópia de ensaio (ela tem os dados da fundação; apague-a depois de examinar)")
    d = sub.add_parser("desfazer")
    d.add_argument("--registro", type=Path, required=True)
    d.add_argument("--aceitar-banco-migrado", action="store_true",
                   help="volta o código mesmo com o banco em esquema novo (decisão da administração)")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "checar":
            res = checar(args.raiz)
            print(json.dumps(res, ensure_ascii=False, indent=1))
            return 0 if res["pode_aplicar"] else 1
        if args.cmd == "aplicar":
            res = aplicar(args.raiz, args.backups, args.padrao_testes, args.manter_ensaio)
        else:
            res = desfazer(args.registro, args.aceitar_banco_migrado)
    except Parada as p:
        print(json.dumps({"ok": False, "etapa": p.etapa, "motivo": p.motivo, **p.detalhes}, ensure_ascii=False,
                         indent=1))
        return 1
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
