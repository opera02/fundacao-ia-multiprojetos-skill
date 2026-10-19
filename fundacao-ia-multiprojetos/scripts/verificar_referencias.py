#!/usr/bin/env python3
"""Confere se os arquivos citados nos Markdown de uma skill/fundação existem.

Verifica: links Markdown relativos `[texto](caminho)`; caminhos em código ou em texto
corrido começando por `references/`, `scripts/`, `assets/` ou `evals/`; e caminhos
relativos em código (`../fluxo-c-operar.md`, `capacidades/04-memoria.md`).
`<skill>/...` (pasta desta skill) é conferido em qualquer lugar, também dentro de comandos, e só
a partir da raiz da skill. Todo caminho é conferido com a grafia exata (maiúsculas e minúsculas).
Convenção da skill: arquivo da própria skill é sempre citado com caminho; nome solto
(`RETOMADA.md`, `relato.md`) designa artefato da fundação do usuário e não é exigido
aqui. Caminhos são resolvidos a partir do arquivo que cita, da raiz e de `references/`.
No pacote instalável (sem `evals/`), citações a `evals/...` são listadas à parte
("fora_do_pacote_instalavel"), não como ausência.

Uso: python verificar_referencias.py [--raiz DIR]   (ausências -> código 1)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
CODE = re.compile(r"`([^`\s]+)`")
# Sem a crase no lookbehind: os trechos de código SEM espaço já saíram do texto (CODE.sub), e os
# que sobram (comandos com espaços) podem começar direto no caminho, como `scripts/x.py criar`.
PLAIN_PATH = re.compile(r"(?<![\w/.-])((?:references|scripts|assets|evals)/[A-Za-z0-9_./\-]*[A-Za-z0-9_\-])")
PREFIXED = re.compile(r"^(?:\.\./)*(?:references|scripts|assets|evals|capacidades|livro)/[A-Za-z0-9_./\-]+$")
RELATIVE = re.compile(r"^(?:\.\./)+[A-Za-z0-9_./\-]+\.(?:md|py|json|csv)$")
IGNORE_PREFIX = ("http://", "https://", "mailto:", "#")
# `<skill>/…` aponta para esta skill: conferido qualquer que seja a primeira pasta (um erro em
# `script/` no lugar de `scripts/` também precisa aparecer).
SKILL_REF = re.compile(r"<skill>/([A-Za-z0-9_./\-]*[A-Za-z0-9_\-])")


def candidates(root: Path, md: Path, target: str) -> list[tuple[Path, str]]:
    return [(md.parent, target), (root, target), (root / "references", target)]


def existe_exato(base: Path, rel: str) -> bool:
    """O caminho existe com a grafia exata de cada parte. No Windows e no macOS o sistema de
    arquivos não distingue maiúsculas, mas o pacote pode ir para um que distingue (Linux)."""
    atual = base
    for parte in (p for p in rel.split("/") if p and p != "."):
        if parte == "..":
            atual = atual.parent
            continue
        try:
            if parte not in os.listdir(atual):
                return False
        except OSError:
            return False
        atual = atual / parte
    return atual.exists()


def check(root: Path) -> dict:
    missing, checked, outside = [], 0, []
    has_evals = (root / "evals").is_dir()
    for md in sorted(root.rglob("*.md")):
        rel_md = md.relative_to(root)
        if any(part in ("evals", "__pycache__") for part in rel_md.parts[:1]):
            continue
        # `<skill>/` = pasta desta skill: some antes da busca, para que `<skill>/scripts/x.py` seja
        # conferido em qualquer lugar — trecho de código, comando com espaços ou bloco de código.
        original = md.read_text(encoding="utf-8")
        text = original.replace("<skill>/", "")
        da_skill = {m.group(1) for m in SKILL_REF.finditer(original)}  # resolvidos só pela raiz
        targets = sorted(da_skill)
        targets += [m.group(1) for m in LINK.finditer(text)]
        for m in CODE.finditer(text):
            t = m.group(1).rstrip(".,;:)")
            if PREFIXED.match(t) or RELATIVE.match(t):
                targets.append(t)
        targets += [m.group(1).rstrip(".") for m in PLAIN_PATH.finditer(CODE.sub(" ", text))]
        seen = set()
        for target in targets:
            if target in seen:
                continue
            seen.add(target)
            if target.startswith(IGNORE_PREFIX) or any(ch in target for ch in "<{*") or "..." in target:
                continue
            clean = target.split("#", 1)[0]
            if not clean:
                continue
            if clean.startswith("evals/") and not has_evals:
                # Pacote instalável (.skill) não leva evals/: a citação vale para o pacote completo.
                outside.append({"arquivo": rel_md.as_posix(), "referencia": target})
                continue
            checked += 1
            onde = [(root, clean)] if target in da_skill else candidates(root, md, clean)
            if not any(existe_exato(base, rel) for base, rel in onde):
                missing.append({"arquivo": rel_md.as_posix(), "referencia": target})
    return {"ok": not missing, "referencias_conferidas": checked, "ausentes": missing,
            "fora_do_pacote_instalavel": outside}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raiz", type=Path, default=Path(__file__).resolve().parents[1])
    args = ap.parse_args()
    result = check(args.raiz.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
