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
- Conflito sem decisão: NADA é escrito; a saída traz o plano revisável; código 3.
- `--atualizar`: substitui os arquivos de código diferentes, guardando antes a versão do destino
  em `registry/kit_backup/<data>/` (retorno = copiar de volta) — use só com referência
  recuperável feita e decisão registrada (fluxo C6).
- `--manter-conflitos`: decisão explícita de estado MISTO: copia os ausentes e preserva os
  conflitos; o registro anota `composicao: "mista"` e a saída sai com código 3.
- Escrita numa área de preparação dentro do destino (`registry/kit_preparo/<data>/`), conferida
  por hash, e promoção arquivo a arquivo; falha na promoção desfaz o que já tinha sido promovido
  (código 5).
- Depois da promoção, confere a composição: todos os arquivos de código do kit no destino com o
  hash da origem → `composicao: "verificada"` e `kit_version` declarada. Sem isso,
  `kit_version` fica nula e `versao_no_destino` mostra o que o `__init__.py` do destino declara.
- Registra em `registry/kit_install.json` cada execução que escreveu algo (estado misto incluído).
- Nunca copia bancos, caches ou segredos; não executa código do destino.

Códigos: 0 instalação completa e verificada (ou simulação sem impedimento) · 2 uso incorreto ·
3 incompleta (conflitos; nada escrito, ou estado misto por decisão) · 4 recusada por contenção ·
5 falha durante a promoção (desfeita).
Uso: python instalar_kit.py --destino RAIZ [--simular] [--atualizar | --manter-conflitos]
Depois: cd RAIZ && python -m fundacao init --admin <identidade-do-titular>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

KIT = Path(__file__).resolve().parents[1] / "assets" / "fundacao-kit"
SKIP_PARTS = {"__pycache__", ".pytest_cache"}
CONFIGURACAO = "registry"  # primeira parte do caminho: configuração local da fundação


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


def dentro(dest: Path, alvo: Path) -> bool:
    """O caminho final, resolvido (seguindo ligações e junções que já existem), fica no destino?"""
    try:
        alvo.resolve().relative_to(dest)
        return True
    except (ValueError, OSError, RuntimeError):
        return False


def planejar(dest: Path, atualizar: bool, carimbo: str) -> dict:
    plano = {"copiar": [], "identicos": [], "conflitos": [], "substituir": [], "config_preservada": [],
             "fora_do_destino": [], "tipo_diferente": []}
    for rel, src in arquivos_do_kit():
        alvo = dest / rel
        if not dentro(dest, alvo):
            plano["fora_do_destino"].append(rel)
            continue
        if not alvo.exists():
            plano["copiar"].append({"path": rel, "sha256": sha(src)})
        elif not alvo.is_file():
            plano["tipo_diferente"].append(rel)
        elif sha(alvo) == sha(src):
            plano["identicos"].append(rel)
        elif rel.split("/", 1)[0] == CONFIGURACAO:
            plano["config_preservada"].append(rel)
        elif atualizar:
            plano["substituir"].append({"path": rel, "sha256_anterior": sha(alvo), "sha256_novo": sha(src)})
        else:
            plano["conflitos"].append(rel)
    for proprio in (Path("registry/kit_install.json"), Path("registry/kit_backup") / carimbo,
                    Path("registry/kit_preparo") / carimbo):
        if not dentro(dest, dest / proprio):
            plano["fora_do_destino"].append(proprio.as_posix())
    return plano


def promover(dest: Path, plano: dict, carimbo: str) -> tuple[str | None, list[str]]:
    """Prepara, confere e promove. Devolve (pasta do backup ou None, erros). Falha = desfeita."""
    origem = {rel: src for rel, src in arquivos_do_kit()}
    preparo = dest / "registry" / "kit_preparo" / carimbo
    backup = dest / "registry" / "kit_backup" / carimbo
    escrever = [(c["path"], c["sha256"]) for c in plano["copiar"]] + \
               [(s["path"], s["sha256_novo"]) for s in plano["substituir"]]
    promovidos: list[tuple[str, bool]] = []  # (rel, existia_antes)
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
            if not dentro(dest, alvo):
                raise OSError(f"caminho saiu do destino durante a instalação: {rel}")
            existia = alvo.exists()
            alvo.parent.mkdir(parents=True, exist_ok=True)
            os.replace(preparo / rel, alvo)
            promovidos.append((rel, existia))
    except OSError as exc:
        for rel, existia in reversed(promovidos):  # desfaz o que já tinha sido promovido
            try:
                if existia:
                    shutil.copy2(backup / rel, dest / rel)
                else:
                    (dest / rel).unlink()
            except OSError:
                pass
        shutil.rmtree(preparo, ignore_errors=True)
        return None, [str(exc)]
    shutil.rmtree(preparo, ignore_errors=True)
    raiz_preparo = dest / "registry" / "kit_preparo"
    if raiz_preparo.is_dir() and not any(raiz_preparo.iterdir()):
        raiz_preparo.rmdir()
    return (str(backup) if plano["substituir"] else None), []


def conferir_composicao(dest: Path) -> list[str]:
    """Arquivos de código do kit ausentes ou diferentes no destino (configuração local à parte)."""
    return [rel for rel, src in arquivos_do_kit() if rel.split("/", 1)[0] != CONFIGURACAO
            and (not (dest / rel).is_file() or sha(dest / rel) != sha(src))]


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
    carimbo = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    versao_antes = kit_version(dest)
    plano = planejar(dest, args.atualizar, carimbo)
    record = {
        "kit_origem": kit_version(KIT), "versao_antes": versao_antes,
        "instalado_em": datetime.now(timezone.utc).isoformat(), "simulacao": args.simular,
        "copiados": plano["copiar"], "identicos": len(plano["identicos"]),
        "conflitos_preservados": plano["conflitos"] + plano["tipo_diferente"],
        "substituidos": plano["substituir"],
        "configuracao_local_preservada": plano["config_preservada"],
        "backup_dos_substituidos": None,
    }
    pendentes = plano["conflitos"] + plano["tipo_diferente"]
    bloqueio = None
    if plano["fora_do_destino"]:
        bloqueio = (4, {"recusado_por_contencao": True, "fora_do_destino": plano["fora_do_destino"][:50],
                        "acao_necessaria": "há ligação ou junção que leva para fora do destino; remova-a e repita"})
    elif plano["tipo_diferente"] and args.atualizar:
        bloqueio = (3, {"acao_necessaria": "pasta onde o kit tem arquivo: resolva à mão e repita"})
    elif pendentes and not (args.atualizar or args.manter_conflitos):
        bloqueio = (3, {"acao_necessaria": "conflitos com alterações locais: nada foi escrito. Revise e repita com "
                                           "--atualizar (guarda a versão do destino para retorno) ou "
                                           "--manter-conflitos (estado misto registrado)"})
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
    if erros:
        record.update(kit_version=None, versao_no_destino=kit_version(dest), composicao="nao_alterada",
                      atualizacao_incompleta=True, erros=erros, desfeito=True)
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 5
    divergentes = conferir_composicao(dest)
    verificada = not divergentes
    record.update(
        kit_version=kit_version(dest) if verificada else None,
        versao_no_destino=kit_version(dest),
        composicao="verificada" if verificada else ("mista" if args.manter_conflitos else "divergente"),
        atualizacao_incompleta=not verificada,
        divergentes_do_kit=divergentes,
    )
    reg = dest / "registry"
    reg.mkdir(parents=True, exist_ok=True)
    log = reg / "kit_install.json"
    history = json.loads(log.read_text(encoding="utf-8")) if log.exists() else []
    history.append(record)
    log.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0 if verificada else 3


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
