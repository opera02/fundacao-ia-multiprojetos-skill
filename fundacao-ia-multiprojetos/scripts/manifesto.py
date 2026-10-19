#!/usr/bin/env python3
"""Manifesto de arquivos com hash e comparação (livro A05, A33, A35; Apêndice E).

Um hash identifica conteúdo; não é backup e não prova que o conteúdo é correto.
Arquivos com aparência de segredo são listados como excluídos e NÃO são lidos.

  criar      --raiz DIR --saida manifesto.json [--texto-canonico] [--rotulo ID] [--excluir GLOB ...]
  verificar  --raiz DIR --manifesto manifesto.json [--excluir GLOB ... --mudar-politica]
  comparar   --a m1.json --b m2.json
  (diferenças -> código 1; uso incorreto -> 2)

O manifesto (formato 2) grava a POLÍTICA efetiva — pastas ignoradas, padrões de segredo,
exclusões extras e texto canônico — e a verificação reconstrói o conjunto com essa mesma
política: criar e verificar descrevem os mesmos arquivos. Mudar a política na verificação exige
`--mudar-politica`, e a mudança aparece em `politica`, separada das mudanças nos arquivos.
Manifesto do formato 1 (sem política gravada): os caminhos que ele lista como excluídos
continuam excluídos, com aviso para refazê-lo.

--texto-canonico: para .md/.txt/.json/.py/.yaml calcula o hash após normalizar
UTF-8, LF e NFC (o mesmo arquivo com CRLF e LF dá o mesmo hash).
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

EXCLUDE_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache", ".pytest_cache"}
SECRET_GLOBS = [".env", ".env.*", "*.pem", "*.key", "*.pfx", "*.p12", "id_rsa*", "*credentials*", "*secret*",
                "auth.json", "*.kdbx"]
TEXT_SUFFIXES = {".md", ".txt", ".json", ".py", ".yaml", ".yml", ".toml", ".csv", ".html", ".sql"}
FORMATO = "fundacao.manifest/2"


def politica_padrao(extras: list[str] | None = None, canonical: bool = False) -> dict:
    return {"pastas_ignoradas": sorted(EXCLUDE_DIRS), "padroes_de_segredo": list(SECRET_GLOBS),
            "exclusoes_extras": sorted(set(extras or [])), "texto_canonico": canonical}


def is_secret(name: str, padroes: list[str] = SECRET_GLOBS) -> bool:
    low = name.lower()
    return any(fnmatch.fnmatch(low, g) for g in padroes)


def file_hash(path: Path, canonical: bool) -> str:
    data = path.read_bytes()
    if canonical and path.suffix.lower() in TEXT_SUFFIXES:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return hashlib.sha256(data).hexdigest()
        text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
        data = unicodedata.normalize("NFC", text).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def build(root: Path, politica: dict, excluidos_extra: set[str] | None = None) -> dict:
    files, excluded = [], []
    pastas = set(politica["pastas_ignoradas"])
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(part in pastas for part in rel.parts[:-1]) or not path.is_file():
            continue
        if (is_secret(path.name, politica["padroes_de_segredo"])
                or any(fnmatch.fnmatch(rel.as_posix(), g) for g in politica["exclusoes_extras"])
                or rel.as_posix() in (excluidos_extra or set())):
            excluded.append({"path": rel.as_posix(), "motivo": "segredo/credencial ou exclusão explícita"})
            continue
        try:
            files.append({"path": rel.as_posix(), "size": path.stat().st_size,
                          "sha256": file_hash(path, politica["texto_canonico"])})
        except OSError as exc:
            excluded.append({"path": rel.as_posix(), "motivo": f"ilegível: {type(exc).__name__}"})
    return {"schema_version": FORMATO, "raiz": root.name,
            "criado_em": datetime.now(timezone.utc).isoformat(), "hash_alg": "sha256",
            "texto_canonico": politica["texto_canonico"], "politica": politica, "arquivos": files, "excluidos": excluded,
            "aviso": "manifesto identifica conteúdo; não é cópia de segurança"}


def diff(a: dict, b: dict) -> dict:
    ma = {f["path"]: f["sha256"] for f in a["arquivos"]}
    mb = {f["path"]: f["sha256"] for f in b["arquivos"]}
    return {
        "alterados": sorted(p for p in ma.keys() & mb.keys() if ma[p] != mb[p]),
        "ausentes": sorted(ma.keys() - mb.keys()),
        "novos": sorted(mb.keys() - ma.keys()),
    }


def _uso(msg: str) -> int:
    print(json.dumps({"erro": msg}, ensure_ascii=False), file=sys.stderr)
    return 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("criar"); c.add_argument("--raiz", type=Path, required=True)
    c.add_argument("--saida", type=Path, required=True); c.add_argument("--texto-canonico", action="store_true")
    c.add_argument("--rotulo"); c.add_argument("--excluir", action="append", default=[])
    v = sub.add_parser("verificar"); v.add_argument("--raiz", type=Path, required=True)
    v.add_argument("--manifesto", type=Path, required=True)
    v.add_argument("--excluir", action="append", default=[], help="exclusões a mais (exige --mudar-politica)")
    v.add_argument("--mudar-politica", action="store_true", help="aceita verificar com política diferente da gravada")
    k = sub.add_parser("comparar"); k.add_argument("--a", type=Path, required=True); k.add_argument("--b", type=Path, required=True)
    args = ap.parse_args()
    if args.cmd == "criar":
        m = build(args.raiz.resolve(), politica_padrao(args.excluir, args.texto_canonico))
        m["rotulo"] = args.rotulo
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        args.saida.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"arquivos": len(m["arquivos"]), "excluidos": len(m["excluidos"]), "saida": str(args.saida)},
                         ensure_ascii=False))
        return 0
    if args.cmd == "verificar":
        ref = json.loads(args.manifesto.read_text(encoding="utf-8"))
        politica = ref.get("politica")
        excluidos_antigos: set[str] = set()
        aviso = None
        if politica is None:  # formato 1: a política extra não foi gravada; os excluídos listados, sim
            politica = politica_padrao([], ref.get("texto_canonico", False))
            excluidos_antigos = {e["path"] for e in ref.get("excluidos", []) if isinstance(e, dict) and "path" in e}
            aviso = ("manifesto do formato 1, sem política gravada: os caminhos que ele lista como excluídos continuam "
                     "excluídos; arquivos novos que caberiam numa exclusão extra aparecem como novos. Refaça-o com "
                     "a versão atual para gravar a política")
        mudanca = None
        if args.excluir:
            if not args.mudar_politica:
                return _uso("verificar com exclusões diferentes das gravadas muda a política; repita com "
                            "--mudar-politica (a mudança aparece separada das mudanças nos arquivos)")
            nova = {**politica, "exclusoes_extras": sorted(set(politica["exclusoes_extras"]) | set(args.excluir))}
            mudanca = {"mudou": nova != politica, "antes": politica, "depois": nova}
            politica = nova
        cur = build(args.raiz.resolve(), politica, excluidos_antigos)
        if mudanca:
            # O que a política nova passa a excluir não é "ausente": sai do domínio da comparação.
            fora = {e["path"] for e in cur["excluidos"]}
            mudanca["passam_a_excluidos"] = sorted(f["path"] for f in ref["arquivos"] if f["path"] in fora)
            ref = {**ref, "arquivos": [f for f in ref["arquivos"] if f["path"] not in fora]}
        d = diff(ref, cur)
        if mudanca:
            d["politica"] = mudanca
        if aviso:
            d["aviso"] = aviso
        print(json.dumps(d, ensure_ascii=False, indent=2))
        return 1 if any(d[k] for k in ("alterados", "ausentes", "novos")) or (mudanca and mudanca["mudou"]) else 0
    a = json.loads(args.a.read_text(encoding="utf-8"))
    b = json.loads(args.b.read_text(encoding="utf-8"))
    d = diff(a, b)
    if a.get("politica") != b.get("politica"):
        d["politica_diferente"] = {"a": a.get("politica"), "b": b.get("politica")}
    print(json.dumps(d, ensure_ascii=False, indent=2))
    return 1 if any(d[k] for k in ("alterados", "ausentes", "novos")) or "politica_diferente" in d else 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
