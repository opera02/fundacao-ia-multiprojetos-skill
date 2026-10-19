#!/usr/bin/env python3
"""Sinais objetivos de compatibilidade de um projeto existente (Fluxo B, etapa B3).

Varre o código-fonte em busca de sinais que pesam na classificação:
  - caminhos absolutos ou '..' saindo da raiz (isolamento por projeto);
  - credenciais embutidas em código ou arquivos de segredo presentes;
  - chamadas de rede/serviços externos (dependência e efeito externo);
  - ausência de testes; dependências declaradas sem versão fixada.
O relatório SUGERE uma classe (integração direta · adaptação por interfaces ·
refatoração delimitada · bloqueio nas condições atuais) com os motivos. A decisão
final é registrada no plano de adaptação, com as evidências do diagnóstico — este
script não lê conteúdo de casos nem valores de segredos (só o nome do arquivo e a
linha onde há atribuição suspeita).

Uso: python sinais_compatibilidade.py --raiz PROJETO [--saida sinais.json]
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path

CODE_SUFFIXES = {".py", ".js", ".ts", ".ps1", ".sh", ".bat", ".cmd", ".rb", ".go", ".java", ".cs"}
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules"}
SECRET_FILES = [".env", ".env.*", "*.pem", "*.key", "*.pfx", "auth.json", "*credentials*"]
ABS_PATH = re.compile(r"""["'](?:[A-Za-z]:[\\/]|/(?:home|Users|mnt|srv|var|etc)/)[^"']+["']""")
PARENT_ESCAPE = re.compile(r"""["'][^"']*\.\.[\\/][^"']*["']""")
CRED_ASSIGN = re.compile(r"""(?i)\b(api[_-]?key|token|senha|password|secret|chave)\w*\s*[:=]\s*["'][^"']{6,}["']""")
NETWORK = re.compile(r"""(?i)\b(requests\.(get|post|put)|urllib\.request|http\.client|httpx\.|fetch\(|socket\.|smtplib|ftplib)""")


def scan(root: Path) -> dict:
    signals = {"caminho_absoluto": [], "escape_da_raiz": [], "credencial_embutida": [],
               "arquivo_de_segredo": [], "rede_ou_servico_externo": [], "dependencia_sem_versao": []}
    has_tests = False
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(p in SKIP_DIRS for p in rel.parts) or not path.is_file():
            continue
        name = path.name.lower()
        if any(fnmatch.fnmatch(name, g) for g in SECRET_FILES):
            signals["arquivo_de_segredo"].append(rel.as_posix())
            continue  # não lê segredos
        if name.startswith("test") or "tests" in rel.parts:
            has_tests = True
        if name in ("requirements.txt",):
            for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                line = line.strip()
                if line and not line.startswith("#") and "==" not in line:
                    signals["dependencia_sem_versao"].append(f"{rel.as_posix()}:{i}")
        if path.suffix.lower() not in CODE_SUFFIXES:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            loc = f"{rel.as_posix()}:{i}"
            if ABS_PATH.search(line):
                signals["caminho_absoluto"].append(loc)
            if PARENT_ESCAPE.search(line):
                signals["escape_da_raiz"].append(loc)
            if CRED_ASSIGN.search(line):
                signals["credencial_embutida"].append(loc)
            if NETWORK.search(line):
                signals["rede_ou_servico_externo"].append(loc)
    reasons = []
    if signals["caminho_absoluto"] or signals["escape_da_raiz"]:
        reasons.append("acesso a caminhos fora da raiz do projeto: isolamento exige refatoração")
    if signals["credencial_embutida"]:
        reasons.append("credencial embutida no código: mover para cofre antes de integrar")
    if signals["rede_ou_servico_externo"]:
        reasons.append("dependência de rede/serviço externo: confirmar acesso, custo e idempotência")
    if not has_tests:
        reasons.append("sem testes: criar caracterização (golden master) antes de mudar")
    if signals["arquivo_de_segredo"]:
        reasons.append("arquivo de segredo presente: excluir de cópias, manifestos e contexto")
    if signals["dependencia_sem_versao"]:
        reasons.append("dependências sem versão fixada: registrar versões antes de reconstruir")
    if (signals["caminho_absoluto"] or signals["escape_da_raiz"]) and signals["rede_ou_servico_externo"] \
            and signals["credencial_embutida"]:
        suggested = "bloqueio nas condições atuais"
    elif signals["caminho_absoluto"] or signals["escape_da_raiz"] or signals["credencial_embutida"]:
        suggested = "refatoração delimitada"
    elif reasons:
        suggested = "adaptação por interfaces"
    else:
        suggested = "integração direta"
    return {"schema_version": "fundacao.sinais_compatibilidade/1", "raiz": root.name,
            "sinais": signals, "tem_testes": has_tests, "classe_sugerida": suggested,
            "motivos": reasons,
            "aviso": "sugestão baseada em sinais estáticos; confirme com o diagnóstico (B1–B2) e registre a decisão"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raiz", type=Path, required=True)
    ap.add_argument("--saida", type=Path)
    args = ap.parse_args()
    result = scan(args.raiz.resolve())
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.saida:
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        args.saida.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
