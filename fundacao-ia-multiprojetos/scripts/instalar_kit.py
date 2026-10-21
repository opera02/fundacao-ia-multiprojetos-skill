#!/usr/bin/env python3
"""Instala ou atualiza o kit de referência numa raiz AUTORIZADA, de forma verificável.

Primeiro o plano, depois a escrita. Antes de gravar qualquer coisa, o instalador compara cada
arquivo do kit com o destino e confere que o caminho final e seus ancestrais (ligações e
junções incluídas) ficam DENTRO do destino; o que apontar para fora recusa a instalação
inteira (código 4, nada escrito).

- Código e modelos (`fundacao/`, `templates/`, `tests/`): ausente → copia; idêntico → ignora;
  diferente (alteração local) → conflito.
- Configuração local (`registry/`: política de rotas, registro de componentes): ausente →
  copia; presente → preservada como está (é estado da fundação), listada em
  `configuracao_local_preservada` quando difere do modelo do kit. Nunca conta como conflito e
  nunca é sobrescrita, nem com `--atualizar`.
- Órfãos (análise do vibe-coding-toolkit, 21/10/2026, proposta 11): arquivo de código que um kit ANTERIOR
  instalou (está em `registry/kit_install.json`) e que o kit novo não tem mais — retirado ou renomeado. Sem
  decisão, conta como conflito (nada escrito); com `--atualizar` vai para o mesmo `registry/kit_backup/<data>-
  <sufixo>/` dos substituídos (retorno = copiar de volta) e entra em `orfaos_retirados`; com
  `--manter-conflitos` fica, e a composição sai "mista". Arquivo que o kit nunca instalou não é órfão.
- Conflito sem decisão: NADA é escrito; a saída traz o plano revisável; código 3.
- `--atualizar`: substitui os arquivos de código diferentes, guardando antes a versão do destino
  em `registry/kit_backup/<data>-<sufixo>/` (retorno = copiar de volta; o sufixo aleatório impede que
  duas execuções no mesmo segundo dividam a pasta) — use só com referência
  recuperável feita e decisão registrada (fluxo C6).
- `--manter-conflitos`: decisão explícita de estado MISTO: copia os ausentes e preserva os
  conflitos; o registro anota `composicao: "mista"` e a saída sai com código 3.
- Escrita numa área de preparação dentro do destino (`registry/kit_preparo/<data>-<sufixo>/`), conferida
  por hash, e promoção arquivo a arquivo; falha na promoção desfaz o que já tinha sido promovido
  (código 5). Se o próprio retorno falhar, a saída não diz que desfez: `desfeito: false`,
  `composicao: "indeterminada"`, cada arquivo não devolvido em `erros` e o caminho do backup em
  `backup_dos_substituidos`; a execução entra no registro (auditoria sobre a 1.4.1, A03).
- Depois da promoção, confere a composição: todos os arquivos de código do kit no destino com o
  hash da origem → `composicao: "verificada"` e `kit_version` declarada. Sem isso,
  `kit_version` fica nula e `versao_no_destino` mostra o que o `__init__.py` do destino declara.
- Registra em `registry/kit_install.json` cada execução que escreveu algo (estado misto incluído).
- Nunca copia bancos, caches ou segredos; não executa código do destino.

Códigos: 0 instalação completa e verificada (ou simulação sem impedimento) · 2 uso incorreto ·
3 incompleta (conflitos; nada escrito, ou estado misto por decisão) · 4 recusada por contenção ·
5 falha durante a promoção (desfeita, ou com retorno incompleto: veja `desfeito`).
Uso: python instalar_kit.py --destino RAIZ [--simular] [--atualizar | --manter-conflitos]
Depois: cd RAIZ && python -m fundacao init --admin <identidade-do-titular>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

KIT = Path(__file__).resolve().parents[1] / "assets" / "fundacao-kit"
SKIP_PARTS = {"__pycache__", ".pytest_cache"}
CONFIGURACAO = "registry"  # primeira parte do caminho: configuração local da fundação
AREAS_DE_CODIGO = ("fundacao", "templates", "tests")  # onde um arquivo retirado pelo kit vira órfão
RETORNO_INCOMPLETO = "retorno incompleto em "  # prefixo, em `erros`, de arquivo que o desfazer não devolveu (A03)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def kit_version(base: Path) -> str:
    init = base / "fundacao" / "__init__.py"
    if not init.exists():
        return "ausente"
    for line in init.read_text(encoding="utf-8").splitlines():
        if line.startswith("KIT_VERSION"):
            return line.split("=", 1)[1].strip().strip('"')
    return "desconhecida"


def arquivos_do_kit() -> list[tuple[str, Path]]:
    out = []
    for src in sorted(KIT.rglob("*")):
        rel = src.relative_to(KIT)
        if not src.is_file() or set(rel.parts) & SKIP_PARTS or src.suffix in (".pyc", ".sqlite"):
            continue
        out.append((rel.as_posix(), src))
    return out


def instalados_antes(dest: Path) -> dict[str, str]:
    """Arquivos que um kit anterior instalou neste destino (copiados, substituídos ou idênticos, segundo
    `registry/kit_install.json`), com o último hash registrado; os já retirados como órfãos saem da lista."""
    try:
        historico = json.loads((dest / "registry" / "kit_install.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    conhecidos: dict[str, str] = {}
    for reg in historico if isinstance(historico, list) else []:
        if not isinstance(reg, dict):
            continue
        for chave, campo in (("copiados", "sha256"), ("identicos_registrados", "sha256"),
                             ("substituidos", "sha256_novo")):
            for item in reg.get(chave) or []:
                if isinstance(item, dict) and item.get("path") and item.get(campo):
                    conhecidos[item["path"]] = item[campo]
        for item in reg.get("orfaos_retirados") or []:
            if isinstance(item, dict):
                conhecidos.pop(item.get("path"), None)
    return conhecidos


def caminho_do_registro_valido(rel) -> bool:
    """Caminho relativo como o instalador grava: barras normais, sem `..` nem `.`, sem raiz, unidade ou `:`. O
    registry/kit_install.json é configuração local (gravável por shell): entrada fora disso é dado adulterado e
    nunca vira órfão a retirar (revisão de segurança da 1.7.0, VCT170-01)."""
    if not isinstance(rel, str) or not rel or chr(92) in rel or ":" in rel or rel.startswith("/"):
        return False
    return all(parte not in ("", ".", "..") for parte in rel.split("/"))


def com_ligacao(raiz: Path, rel: str) -> bool:
    """Algum componente do caminho, abaixo da raiz, é ligação simbólica ou junção? Conferido sem seguir (como o
    guarda_caminho.py e o backup do kit): `dentro()` resolve a ligação e aceitaria `tests/elo -> .claude`
    (revisão de segurança da 1.7.0, VCT170-04)."""
    atual = Path(raiz)
    for parte in rel.split("/"):
        atual = atual / parte
        try:
            st = os.lstat(atual)
        except OSError:
            return False  # o resto do caminho ainda não existe
        if stat.S_ISLNK(st.st_mode) or getattr(st, "st_reparse_tag", 0) & 0x20000000:  # substituto de nome
            return True
    return False


def dentro(dest: Path, alvo: Path) -> bool:
    """O caminho final, resolvido (seguindo ligações e junções que já existem), fica no destino?"""
    try:
        alvo.resolve().relative_to(dest)
        return True
    except (ValueError, OSError, RuntimeError):
        return False


def planejar(dest: Path, atualizar: bool, carimbo: str) -> dict:
    plano = {"copiar": [], "identicos": [], "identicos_registrados": [], "conflitos": [], "substituir": [],
             "config_preservada": [], "fora_do_destino": [], "tipo_diferente": [], "orfaos": [], "retirar": [],
             "entradas_invalidas": []}
    do_kit = arquivos_do_kit()
    for rel, src in do_kit:
        alvo = dest / rel
        if com_ligacao(dest, rel) or not dentro(dest, alvo):
            plano["fora_do_destino"].append(rel)
            continue
        if not alvo.exists():
            plano["copiar"].append({"path": rel, "sha256": sha(src)})
        elif not alvo.is_file():
            plano["tipo_diferente"].append(rel)
        elif sha(alvo) == sha(src):
            plano["identicos"].append(rel)
            plano["identicos_registrados"].append({"path": rel, "sha256": sha(src)})
        elif rel.split("/", 1)[0] == CONFIGURACAO:
            plano["config_preservada"].append(rel)
        elif atualizar:
            plano["substituir"].append({"path": rel, "sha256_anterior": sha(alvo), "sha256_novo": sha(src)})
        else:
            plano["conflitos"].append(rel)
    no_kit = {rel for rel, _ in do_kit}
    for rel, registrado in sorted(instalados_antes(dest).items()):
        if not caminho_do_registro_valido(rel):
            plano["entradas_invalidas"].append(rel)
            continue
        alvo = dest / rel
        if rel in no_kit or rel.split("/", 1)[0] not in AREAS_DE_CODIGO or not alvo.is_file():
            continue
        if com_ligacao(dest, rel) or not dentro(dest, alvo):
            plano["fora_do_destino"].append(rel)
            continue
        atual = sha(alvo)
        plano["orfaos"].append({"path": rel, "sha256": atual, "alterado_localmente": atual != registrado})
    if atualizar:
        plano["retirar"] = list(plano["orfaos"])
    for proprio in (Path("registry/kit_install.json"), Path("registry/kit_backup") / carimbo,
                    Path("registry/kit_preparo") / carimbo):
        if not dentro(dest, dest / proprio):
            plano["fora_do_destino"].append(proprio.as_posix())
    return plano


def promover(dest: Path, plano: dict, carimbo: str) -> tuple[str | None, list[str]]:
    """Prepara, confere e promove. Devolve (pasta do backup, se existir, ou None; erros). Falha = desfeita; o
    que o desfazer não conseguir devolver vai para `erros` com o prefixo RETORNO_INCOMPLETO, nunca é engolido."""
    origem = {rel: src for rel, src in arquivos_do_kit()}
    preparo = dest / "registry" / "kit_preparo" / carimbo
    backup = dest / "registry" / "kit_backup" / carimbo
    escrever = [(c["path"], c["sha256"]) for c in plano["copiar"]] + \
               [(s["path"], s["sha256_novo"]) for s in plano["substituir"]]
    promovidos: list[tuple[str, bool]] = []  # (rel, existia_antes)
    retirados: list[str] = []  # órfãos já tirados do destino (estão no backup)
    try:
        for rel, esperado in escrever:  # 1. preparação, conferida por hash
            p = preparo / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origem[rel], p)
            if sha(p) != esperado:
                raise OSError(f"cópia preparada diverge da origem: {rel}")
        for s in plano["substituir"]:  # 2. cópia da versão do destino, para retorno
            g = backup / s["path"]
            g.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest / s["path"], g)
            if sha(g) != s["sha256_anterior"]:
                raise OSError(f"cópia de retorno diverge do destino: {s['path']}")
        for rel, _ in escrever:  # 3. promoção arquivo a arquivo (renomeação no mesmo volume)
            alvo = dest / rel
            if com_ligacao(dest, rel) or not dentro(dest, alvo):
                raise OSError(f"caminho saiu do destino durante a instalação: {rel}")
            existia = alvo.exists()
            alvo.parent.mkdir(parents=True, exist_ok=True)
            os.replace(preparo / rel, alvo)
            promovidos.append((rel, existia))
        for o in plano["retirar"]:  # 4. órfãos: cópia conferida no backup e só então saem do destino
            alvo, g = dest / o["path"], backup / o["path"]
            if com_ligacao(dest, o["path"]) or not dentro(dest, alvo):
                raise OSError(f"caminho saiu do destino durante a instalação: {o['path']}")
            g.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(alvo, g)
            if sha(g) != o["sha256"]:
                raise OSError(f"cópia de retorno do órfão diverge do destino: {o['path']}")
            alvo.unlink()
            retirados.append(o["path"])
    except OSError as exc:
        erros = [str(exc)]
        for rel in reversed(retirados):  # devolve os órfãos já retirados
            try:
                shutil.copy2(backup / rel, dest / rel)
            except OSError as falha:
                erros.append(f"{RETORNO_INCOMPLETO}{rel} (copie de volta de {backup / rel}): {falha}")
        for rel, existia in reversed(promovidos):  # desfaz o que já tinha sido promovido
            try:
                if existia:
                    shutil.copy2(backup / rel, dest / rel)
                else:
                    (dest / rel).unlink()
            except OSError as falha:
                acao = f"copie de volta de {backup / rel}" if existia else "apague o arquivo novo"
                erros.append(f"{RETORNO_INCOMPLETO}{rel} ({acao}): {falha}")
        shutil.rmtree(preparo, ignore_errors=True)
        return (str(backup) if backup.is_dir() else None), erros
    shutil.rmtree(preparo, ignore_errors=True)
    raiz_preparo = dest / "registry" / "kit_preparo"
    if raiz_preparo.is_dir() and not any(raiz_preparo.iterdir()):
        raiz_preparo.rmdir()
    return (str(backup) if plano["substituir"] or plano["retirar"] else None), []


def registrar(dest: Path, record: dict) -> None:
    """Acrescenta a execução a `registry/kit_install.json`."""
    reg = dest / "registry"
    reg.mkdir(parents=True, exist_ok=True)
    log = reg / "kit_install.json"
    history = json.loads(log.read_text(encoding="utf-8")) if log.exists() else []
    history.append(record)
    log.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def conferir_composicao(dest: Path, orfaos: list[dict] | None = None) -> list[str]:
    """Arquivos de código do kit ausentes ou diferentes no destino (configuração local à parte) e órfãos que
    continuam no destino."""
    divergentes = [rel for rel, src in arquivos_do_kit() if rel.split("/", 1)[0] != CONFIGURACAO
                   and (not (dest / rel).is_file() or sha(dest / rel) != sha(src))]
    return divergentes + [o["path"] for o in orfaos or [] if (dest / o["path"]).exists()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--destino", type=Path, required=True)
    ap.add_argument("--simular", action="store_true", help="só relata o que faria (nada é escrito)")
    decisao = ap.add_mutually_exclusive_group()
    decisao.add_argument("--atualizar", action="store_true",
                         help="substitui arquivos de código diferentes, guardando a versão anterior para retorno")
    decisao.add_argument("--manter-conflitos", action="store_true",
                         help="estado misto por decisão explícita: copia os ausentes e preserva os conflitos")
    args = ap.parse_args()
    dest = args.destino.resolve()
    # Sufixo aleatório: duas execuções no mesmo segundo não dividem backup nem preparo (A03).
    carimbo = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    versao_antes = kit_version(dest)
    plano = planejar(dest, args.atualizar, carimbo)
    record = {
        "kit_origem": kit_version(KIT), "versao_antes": versao_antes,
        "instalado_em": datetime.now(timezone.utc).isoformat(), "simulacao": args.simular,
        "copiados": plano["copiar"], "identicos": len(plano["identicos"]),
        "identicos_registrados": plano["identicos_registrados"], "orfaos": plano["orfaos"],
        "conflitos_preservados": plano["conflitos"] + plano["tipo_diferente"],
        "substituidos": plano["substituir"],
        "configuracao_local_preservada": plano["config_preservada"],
        "entradas_invalidas": plano["entradas_invalidas"],  # ignoradas: registry/kit_install.json adulterado?
        "backup_dos_substituidos": None,
    }
    orfaos_pendentes = [] if args.atualizar else [o["path"] for o in plano["orfaos"]]
    pendentes = plano["conflitos"] + plano["tipo_diferente"] + orfaos_pendentes
    bloqueio = None
    if plano["fora_do_destino"]:
        bloqueio = (4, {"recusado_por_contencao": True, "fora_do_destino": plano["fora_do_destino"][:50],
                        "acao_necessaria": "há ligação ou junção que leva para fora do destino; remova-a e repita"})
    elif plano["tipo_diferente"] and args.atualizar:
        bloqueio = (3, {"acao_necessaria": "pasta onde o kit tem arquivo: resolva à mão e repita"})
    elif pendentes and not (args.atualizar or args.manter_conflitos):
        bloqueio = (3, {"acao_necessaria": "conflitos com alterações locais ou arquivos que o kit novo retirou "
                                           "(órfãos): nada foi escrito. Revise e repita com --atualizar (guarda "
                                           "a versão do destino e os órfãos para retorno) ou --manter-conflitos "
                                           "(estado misto registrado)"})
    # Com --manter-conflitos e pendências, segue: estado misto por decisão explícita.
    if bloqueio or args.simular:
        codigo = bloqueio[0] if bloqueio else (3 if pendentes else 0)
        record.update(bloqueio[1] if bloqueio else {})
        record.update(kit_version=None, versao_no_destino=versao_antes,
                      composicao="simulacao" if args.simular and not bloqueio else "nao_alterada",
                      atualizacao_incompleta=codigo != 0, nada_escrito=True)
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return codigo
    backup, erros = promover(dest, plano, carimbo)
    record["backup_dos_substituidos"] = backup
    record["orfaos_retirados"] = [] if erros else plano["retirar"]
    if erros:
        retorno_incompleto = any(e.startswith(RETORNO_INCOMPLETO) for e in erros)
        record.update(kit_version=None, versao_no_destino=kit_version(dest),
                      composicao="indeterminada" if retorno_incompleto else "nao_alterada",
                      atualizacao_incompleta=True, erros=erros, desfeito=not retorno_incompleto)
        if retorno_incompleto:
            record["acao_necessaria"] = ("a promoção falhou e o retorno também: o destino ficou com parte do kit "
                                         "novo. Siga cada item 'retorno incompleto' de `erros` (a versão anterior "
                                         "está em `backup_dos_substituidos`) e confira antes de repetir")
            registrar(dest, record)  # escreveu algo que ficou no destino
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 5
    divergentes = conferir_composicao(dest, plano["orfaos"])
    verificada = not divergentes
    record.update(
        kit_version=kit_version(dest) if verificada else None,
        versao_no_destino=kit_version(dest),
        composicao="verificada" if verificada else ("mista" if args.manter_conflitos else "divergente"),
        atualizacao_incompleta=not verificada,
        divergentes_do_kit=divergentes,
    )
    registrar(dest, record)
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0 if verificada else 3


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
