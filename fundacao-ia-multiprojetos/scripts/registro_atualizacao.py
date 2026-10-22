#!/usr/bin/env python3
"""Registro, âncora e volta (`desfazer`) da atualização da fundação: a parte do `atualizar_fundacao.py` que grava o
registro e desfaz a atualização, separada dele na 1.7.7 (revisão de segurança), quando ele passou de 800 linhas. O
comando continua lá: `atualizar_fundacao.py desfazer --registro <arq>`.

- `gravar`: o registro em evidence/atualizacoes/ e, com `ancorar`, o SHA-256 dele em registry/atualizacoes.jsonl, fora
  da pasta de evidências (auditoria Codex Security da 1.7.6, #10), sem seguir ligação nem vínculo físico
  (`gravacao_segura.py`; R177-ATU-03);
- `desfazer`: só o registro da própria raiz, ancorado, com caminhos nas áreas de código do kit; só se o banco não mudou
  de esquema e o código ainda é o que a atualização deixou (`sha256_novo`): repetido, ou depois de outra atualização,
  recusa. Devolve os bytes que conferiu, por temporário e `os.replace`, e acrescenta a volta ao
  registry/kit_install.json.
Recusa ou falha = `Parada` (etapa e motivo), que o `atualizar_fundacao.py` mostra em JSON.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
if str(AQUI) not in sys.path:  # carregado por caminho (testes): os módulos vizinhos também têm de ser achados
    sys.path.append(str(AQUI))
import gravacao_segura as gravacao  # noqa: E402  (gravação sem seguir ligação nem vínculo físico; R177-ATU-03)
from codigo_conferido import AREAS_DE_CODIGO  # noqa: E402  (fundacao/, templates/, tests/)

LIVRO = Path("registry") / "atualizacoes.jsonl"  # âncora (SHA-256) de cada registro que o `desfazer` pode usar (#10)
# Onde a atualização e o `desfazer` gravam: ligação no caminho ou vínculo físico ali recusa (R177-ATU-03).
GRAVADOS = ("registry/kit_backup", "registry/kit_install.json", LIVRO.as_posix(), "evidence/atualizacoes")
# Algum componente do caminho, abaixo da raiz, é ligação simbólica ou junção? Sem seguir: `dentro()` resolve a ligação
# e aceitaria `tests/elo -> .claude` (revisão de segurança da 1.7.0, VCT170-04).
com_ligacao = gravacao.com_ligacao


class Parada(Exception):
    """Interrompe `aplicar` ou `desfazer` na etapa indicada; nada além do já relatado foi feito."""

    def __init__(self, etapa: str, motivo: str, **detalhes):
        super().__init__(motivo)
        self.etapa, self.motivo, self.detalhes = etapa, motivo, detalhes


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def versao_do_kit(base: Path) -> str | None:
    init = Path(base) / "fundacao" / "__init__.py"
    if not init.is_file():
        return None
    m = re.search(r'^KIT_VERSION\s*=\s*"([^"]+)"', init.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else None


def user_version(raiz: Path):
    db = Path(raiz) / "state" / "state.sqlite"
    if not db.is_file():
        return None
    con = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        return con.execute("PRAGMA user_version").fetchone()[0]
    finally:
        con.close()


def caminho_do_registro_valido(rel) -> bool:
    """Como no instalar_kit.py: relativo, barras normais, sem `..`, `.`, raiz, unidade ou `:` (VCT170-01/02)."""
    if not isinstance(rel, str) or not rel or chr(92) in rel or ":" in rel or rel.startswith("/"):
        return False
    return all(parte not in ("", ".", "..") for parte in rel.split("/"))


def desvio(desviados: list, quem: str) -> str:
    return ("ligação, junção ou vínculo físico onde " + quem + " grava (" + ", ".join(desviados) + "): a cópia das "
            "instruções, o registro, a âncora ou o registro da instalação iriam para fora da raiz; troque por pasta ou "
            "arquivo comum e repita (R177-ATU-03)")


def gravar(raiz: Path, nome: str, dados: dict, ancorar: bool = False) -> Path:
    """Grava o registro em evidence/atualizacoes/. Com `ancorar` (registro que o `desfazer` pode usar: atualização
    promovida, mesmo que falhe depois, ou só instruções), acrescenta o SHA-256 dele em registry/atualizacoes.jsonl,
    fora da pasta de evidências: registro alterado depois não confere (auditoria Codex Security da 1.7.6, #10).
    Sem seguir ligação nem vínculo físico: registro criado com exclusividade, âncora acrescentada pelo padrão do kit;
    recusa vira Parada na etapa `registro` (R177-ATU-03)."""
    conteudo = (json.dumps(dados, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    try:
        arq = gravacao.pasta_sem_ligacao(raiz, "evidence/atualizacoes") / nome
        gravacao.criar(arq, conteudo)
        if ancorar:
            linha = {"registro": arq.relative_to(raiz).as_posix(), "sha256": hashlib.sha256(conteudo).hexdigest(),
                     "gravado_em": agora()}
            gravacao.pasta_sem_ligacao(raiz, LIVRO.parent.as_posix())
            gravacao.anexar(Path(raiz) / LIVRO, (json.dumps(linha, ensure_ascii=False) + "\n").encode("utf-8"))
    except OSError as exc:
        raise Parada("registro", "o registro ou a âncora não foi gravado (" + type(exc).__name__ + ": "
                     + str(exc)[:200] + ")")
    return arq


INSTRUCOES = ("AGENTS.md", "CLAUDE.md")  # os únicos arquivos que as instruções da raiz tocam


def _dentro(caminho, base: Path) -> bool:
    try:
        Path(caminho).resolve().relative_to(Path(base).resolve())
        return True
    except (ValueError, OSError, RuntimeError):
        return False


def _conferir_registro(registro_arq: Path, reg: dict) -> Path:
    """O registro é dado (fica em evidence/, gravável por shell): só vale o desta raiz, com caminhos relativos sem
    `..`, cópias dentro de registry/kit_backup e instruções só AGENTS.md e CLAUDE.md (revisão de segurança da 1.7.0,
    VCT170-02). Cada categoria do plano do kit (substituídos, copiados, órfãos retirados) só pode tocar as áreas de
    código do kit — nunca state/, projects/, os dados de registry/ nem evidence/ — e traz os hashes que o `desfazer`
    confere (auditoria Codex Security da 1.7.6, #10; o `sha256_novo` dos substituídos desde a revisão de segurança da
    1.7.7). Devolve a raiz; qualquer desvio para antes de alterar o que for."""
    raiz = Path(registro_arq).resolve().parents[2]  # <raiz>/evidence/atualizacoes/<registro>.json
    if Path(str(reg.get("raiz") or "")).resolve() != raiz:
        raise Parada("desfazer", "o registro diz que a raiz é " + str(reg.get("raiz")) + ", mas ele está em " + str(raiz)
                     + ": só se desfaz a atualização registrada dentro da própria raiz; nada foi alterado")
    guarda = raiz / "registry" / "kit_backup"
    kit = (reg.get("promocao") or {}).get("instalar_kit") or {}
    instr = reg.get("instrucoes_raiz") or {}
    problemas = [campo + " fora de registry/kit_backup" for campo, pasta in
                 (("backup_dos_substituidos", kit.get("backup_dos_substituidos")), ("copia", instr.get("copia")))
                 if pasta and not _dentro(pasta, guarda)]
    for chave, campos in (("substituidos", ("sha256_anterior", "sha256_novo")), ("copiados", ("sha256",)),
                          ("orfaos_retirados", ("sha256",))):
        for item in kit.get(chave) or []:
            rel = item.get("path") if isinstance(item, dict) else None
            if not caminho_do_registro_valido(rel) or com_ligacao(raiz, rel) or not _dentro(raiz / rel, raiz):
                problemas.append(chave + ": caminho inválido ou atrás de ligação " + repr(rel)[:80])
            elif rel.split("/", 1)[0] not in AREAS_DE_CODIGO:
                problemas.append(chave + ": fora das áreas de código do kit (" + "/, ".join(AREAS_DE_CODIGO) + "/): "
                                 + rel)
            elif not all(re.fullmatch(r"[0-9a-f]{64}", str(item.get(c) or "")) for c in campos):
                problemas.append(chave + ": sem o SHA-256 de " + rel)
    nomes = set(instr.get("acoes") or {}) | {i.get("path") for i in instr.get("guardados") or [] if isinstance(i, dict)}
    if not nomes <= set(INSTRUCOES):
        problemas.append("instrucoes_raiz: só AGENTS.md e CLAUDE.md")
    if problemas:
        raise Parada("desfazer", "o registro tem caminho fora do que a atualização grava (" + "; ".join(problemas[:5])
                     + "): pode ter sido adulterado; nada foi alterado")
    return raiz


def _conferir_ancora(raiz: Path, registro_arq: Path, conteudo: bytes) -> None:
    """O registro só vale com o SHA-256 que o `aplicar` anotou em registry/atualizacoes.jsonl ao gravá-lo (#10):
    registro alterado depois, forjado ou gravado por versão anterior do atualizador (sem âncora) para aqui."""
    rel = Path(registro_arq).resolve().relative_to(raiz).as_posix()
    digest = hashlib.sha256(conteudo).hexdigest()
    try:
        linhas = (raiz / LIVRO).read_text(encoding="utf-8").splitlines()
    except OSError:
        linhas = []
    for linha in linhas:
        try:
            item = json.loads(linha)
        except ValueError:
            continue
        if isinstance(item, dict) and item.get("registro") == rel and item.get("sha256") == digest:
            return
    raise Parada("desfazer", "o registro não confere com a âncora em " + LIVRO.as_posix() + " (foi alterado depois de "
                 "gravado, não foi gravado pelo `aplicar` ou é de versão anterior do atualizador): nada foi alterado. "
                 "Para voltar, restaure a cópia ANTES numa pasta nova (fluxo C9)")


def _registrar_volta(raiz: Path, kit: dict, apagados: list, registro: str, versao) -> str:
    """Acrescenta a volta ao registry/kit_install.json, no formato do instalar_kit.py: os devolvidos e os órfãos
    recolocados como `copiados` (com o hash que têm agora) e os apagados como `orfaos_retirados`. Sem isso, o registro
    continuaria com os hashes do kit novo e o `checar` seguinte acusaria os devolvidos como alterados localmente e os
    órfãos recolocados como executáveis desconhecidos (achado na validação da 1.7.7)."""
    entrada = {"origem": "atualizar_fundacao.py desfazer", "registro_desfeito": registro,
               "instalado_em": datetime.now(timezone.utc).isoformat(), "simulacao": False, "versao_no_destino": versao,
               "copiados": [{"path": i["path"], "sha256": i["sha256_anterior"]} for i in kit.get("substituidos", [])]
               + [{"path": i["path"], "sha256": i["sha256"]} for i in kit.get("orfaos_retirados", [])],
               "orfaos_retirados": [{"path": i["path"], "sha256": i["sha256"]} for i in kit.get("copiados", [])
                                    if i["path"] in apagados]}
    arq = Path(raiz) / "registry" / "kit_install.json"
    try:
        historico = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else []
        if not isinstance(historico, list):
            return "registro com formato inesperado"
        historico.append(entrada)
        gravacao.publicar(arq, json.dumps(historico, ensure_ascii=False, indent=2).encode("utf-8"))  # R177-ATU-03
    except (OSError, ValueError, RecursionError) as exc:  # aninhamento que estoura a pilha também (R177C-B-04)
        return type(exc).__name__ + ": " + str(exc)[:200]
    return "atualizado"


def _lidos_conferidos(base: Path | None, itens: list, onde: str) -> dict:
    """Bytes de cada (caminho, sha256) guardado em `base`, lidos uma vez e conferidos: o que é conferido é o que é
    gravado de volta. Ausente, atrás de ligação ou diferente para antes de alterar qualquer arquivo."""
    lidos = {}
    for rel, esperado in itens:
        origem = base / rel if base else None
        dados = origem.read_bytes() if origem and not com_ligacao(base, rel) and origem.is_file() else None
        if dados is None or hashlib.sha256(dados).hexdigest() != esperado:
            raise Parada("desfazer", "a cópia anterior de " + rel + " está ausente ou diferente em " + onde
                         + "; nada foi alterado")
        lidos[rel] = dados
    return lidos


def desfazer(registro_arq: Path, aceitar_banco_migrado: bool) -> dict:
    """Devolve o código anterior à atualização registrada, se o esquema do banco não mudou e o código ainda é o que a
    atualização deixou. Grava sem seguir ligação nem vínculo físico (R177-ATU-03)."""
    conteudo = Path(registro_arq).read_bytes()  # lido uma vez: o que é conferido é o que é usado
    try:
        reg = json.loads(conteudo.decode("utf-8"))
    except ValueError as exc:
        raise Parada("desfazer", "registro ilegível (" + type(exc).__name__ + "): nada foi alterado")
    if not isinstance(reg, dict):
        raise Parada("desfazer", "registro sem a estrutura do `aplicar`: nada foi alterado")
    raiz = _conferir_registro(Path(registro_arq), reg)
    kit = (reg.get("promocao") or {}).get("instalar_kit") or {}  # registro só de instruções não tem plano do kit
    atual = user_version(raiz)
    if atual != reg.get("user_version_antes") and not aceitar_banco_migrado:
        raise Parada("desfazer", "o banco mudou de esquema desde a atualização (user_version "
                     + str(reg.get("user_version_antes")) + " -> " + str(atual) + "): voltar só o código deixaria "
                     "o kit antigo com um banco novo. Restaure a cópia ANTES numa pasta nova (fluxo C9)",
                     copia_antes=(reg.get("antes") or {}).get("pasta"))
    _conferir_ancora(raiz, Path(registro_arq), conteudo)
    desviados = gravacao.desviados(raiz, GRAVADOS)
    if desviados:
        raise Parada("desfazer", desvio(desviados, "o `desfazer`") + "; nada foi alterado")
    # O código tem de ser o que a atualização deixou: repetido, ou depois de outra atualização, o `desfazer` poria a
    # versão anterior por cima de outra (observação da revisão de segurança da 1.7.7).
    mudou = [i["path"] for i in kit.get("substituidos", [])
             if not (raiz / i["path"]).is_file() or sha(raiz / i["path"]) != i["sha256_novo"]]
    mudou += [i["path"] for i in kit.get("orfaos_retirados", []) if (raiz / i["path"]).exists()]
    if mudou:
        raise Parada("desfazer", "o código mudou depois da atualização (" + ", ".join(mudou[:5]) + "): ela já foi "
                     "desfeita, outra atualização a seguiu ou houve alteração local; nada foi alterado. Para voltar, "
                     "restaure a cópia ANTES numa pasta nova (fluxo C9)",
                     copia_antes=(reg.get("antes") or {}).get("pasta"))
    backup = Path(kit["backup_dos_substituidos"]) if kit.get("backup_dos_substituidos") else None
    lidos = _lidos_conferidos(backup, [(i["path"], i["sha256_anterior"]) for i in kit.get("substituidos", [])]
                              + [(i["path"], i["sha256"]) for i in kit.get("orfaos_retirados", [])],
                              "registry/kit_backup")
    instr = reg.get("instrucoes_raiz") or {}
    copia_instr = Path(instr["copia"]) if instr.get("copia") else None
    lidas = _lidos_conferidos(copia_instr, [(i["path"], i["sha256_anterior"]) for i in instr.get("guardados", [])],
                              str(copia_instr))
    devolvidos, apagados, orfaos = [], [], []
    for item in kit.get("substituidos", []):
        gravacao.publicar(raiz / item["path"], lidos[item["path"]])
        devolvidos.append(item["path"])
    for item in kit.get("orfaos_retirados", []):  # o que o kit novo tinha retirado volta ao lugar
        (raiz / item["path"]).parent.mkdir(parents=True, exist_ok=True)
        gravacao.publicar(raiz / item["path"], lidos[item["path"]])
        orfaos.append(item["path"])
    for item in kit.get("copiados", []):
        alvo = raiz / item["path"]
        if alvo.is_file() and sha(alvo) == item["sha256"]:
            alvo.unlink()
            apagados.append(item["path"])
    instrucoes = {"devolvidas": [], "apagadas": [], "mantidas": []}
    com_copia = {item["path"] for item in instr.get("guardados", [])}
    for nome, acao in (instr.get("acoes") or {}).items() if instr.get("gerado") else ():
        alvo = raiz / nome
        if acao == "igual" or not alvo.is_file():
            continue
        if sha(alvo) != instr["sha256"][nome]:  # editado depois da atualização: fica como está
            instrucoes["mantidas"].append(nome)
        elif nome in com_copia:
            gravacao.publicar(alvo, lidas[nome])
            instrucoes["devolvidas"].append(nome)
        elif acao == "criar":
            alvo.unlink()
            instrucoes["apagadas"].append(nome)
    versao = versao_do_kit(raiz)
    res = {"ok": True, "kit_na_raiz": versao, "devolvidos": devolvidos, "apagados": apagados,
           "orfaos_devolvidos": orfaos, "instrucoes": instrucoes,
           "resumo": ["Código devolvido ao kit " + str(versao) + ": " + str(len(devolvidos))
                      + " arquivo(s) devolvido(s), " + str(len(orfaos)) + " retirado(s) recolocado(s) e "
                      + str(len(apagados)) + " apagado(s). O banco não foi tocado."] if kit else
                     ["O registro era só das instruções da raiz: o código e o banco não foram tocados."]}
    if instrucoes["devolvidas"] or instrucoes["apagadas"]:
        res["resumo"].append("Instruções da raiz: " + ", ".join(
            [n + " devolvido" for n in instrucoes["devolvidas"]] + [n + " apagado" for n in instrucoes["apagadas"]])
            + ".")
    if devolvidos or orfaos or apagados:
        res["registro_da_instalacao"] = _registrar_volta(raiz, kit, apagados, Path(registro_arq).name, versao)
        if res["registro_da_instalacao"] != "atualizado":
            res["resumo"].append("Atenção: registry/kit_install.json não foi atualizado (" + res["registro_da_instalacao"]
                                 + "); o próximo `checar` pode acusar os arquivos devolvidos como alterados.")
    if instrucoes["mantidas"]:
        res["resumo"].append("Instruções da raiz editadas depois da atualização ficaram como estão: "
                             + ", ".join(instrucoes["mantidas"]) + ".")
    nome = "desfeita-" + Path(registro_arq).stem + "-" + agora() + ".json"
    try:  # a volta já foi feita: a falha do registro dela vai ao resumo, não esconde o que mudou
        res["registro"] = str(gravar(raiz, nome, {**res, "atualizacao": str(registro_arq)}))
    except Parada as q:
        res["registro"] = None
        res["resumo"].append("Atenção: " + q.motivo + "; a volta acima foi feita.")
    return res
