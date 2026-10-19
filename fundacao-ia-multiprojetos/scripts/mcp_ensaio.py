#!/usr/bin/env python3
"""Ensaio local do MCP (livro A11C; R34): servidor da fundação em PROCESSO SEPARADO (stdio),
descoberta, chamada autorizada, negativa entre projetos e encerramento. Sem rede.

  python mcp_ensaio.py --raiz <fundacao> --projeto <autorizado> --outro <nao-autorizado> [--saida ensaio.json]

Pré-requisitos (conferidos aqui; nada é instalado): pacote `mcp` (SDK Python 2.x) já presente;
`FUNDACAO_PRINCIPAL` definida pelo lançador; banco da fundação existente.
Códigos: 0 tudo conferiu · 1 alguma verificação falhou · 3 bloqueado (pré-requisito ausente).
Real × simulado: servidor e cliente são o SDK oficial em processos locais (real-local); a
integração com o host (registrar o servidor no Claude Code/Codex) é outra etapa, que altera a
configuração do usuário e exige decisão dele.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import importlib.util
import json
import os
import sys
from pathlib import Path


def bloqueado(motivo: str, saida: Path | None) -> int:
    texto = json.dumps({"estado": "bloqueado", "motivo": motivo}, ensure_ascii=False, indent=2)
    if saida:
        saida.parent.mkdir(parents=True, exist_ok=True)
        saida.write_text(texto, encoding="utf-8")
    print(texto)
    return 3


async def roteiro(raiz: Path, projeto: str, outro: str) -> dict:
    from mcp import Client, StdioServerParameters

    env = {k: v for k, v in os.environ.items() if k in (
        "PATH", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR", "USERNAME", "USERPROFILE", "HOME", "FUNDACAO_PRINCIPAL")}
    env.update({"PYTHONPATH": str(raiz), "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    params = StdioServerParameters(command=sys.executable, args=["-B", "-m", "fundacao.mcp_servidor", "--raiz", str(raiz)],
                                   env=env, cwd=str(raiz))
    out: dict = {}
    async with Client(params) as client:
        # Versão de protocolo negociada e identificação do servidor (critério de aceite do R34).
        out["protocolo_negociado"] = client.protocol_version
        info = client.server_info
        out["servidor"] = {"nome": getattr(info, "name", None), "versao": getattr(info, "version", None)} if info else None
        out["ferramentas"] = sorted(t.name for t in (await client.list_tools()).tools)
        vis = await client.call_tool("listar_projetos", {})
        out["projetos_visiveis"] = vis.structured_content.get("result") if vis.structured_content else None
        proprio = await client.call_tool("listar_documentos", {"projeto": projeto})
        out["chamada_autorizada"] = {"erro": proprio.is_error,
                                     "documentos": (proprio.structured_content or {}).get("result")}
        alheio = await client.call_tool("listar_documentos", {"projeto": outro})
        out["negativa_outro_projeto"] = {"erro": alheio.is_error,
                                         "mensagem": " ".join(getattr(c, "text", "") for c in alheio.content)}
    out["encerrado"] = True  # o contexto fechou o stdio; o processo do servidor terminou
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raiz", type=Path, required=True)
    ap.add_argument("--projeto", required=True)
    ap.add_argument("--outro", required=True)
    ap.add_argument("--saida", type=Path)
    a = ap.parse_args()
    raiz = a.raiz.resolve()
    if importlib.util.find_spec("mcp") is None:
        return bloqueado("pacote mcp ausente; instalar exige autorização (venv descartável)", a.saida)
    if not os.environ.get("FUNDACAO_PRINCIPAL"):
        return bloqueado("FUNDACAO_PRINCIPAL não definida pelo lançador", a.saida)
    if not (raiz / "state" / "state.sqlite").is_file() or not (raiz / "fundacao" / "mcp_servidor.py").is_file():
        return bloqueado("raiz sem fundação ou sem o servidor MCP do kit (fundacao/mcp_servidor.py)", a.saida)
    res = asyncio.run(roteiro(raiz, a.projeto, a.outro))
    res.update({
        "estado": "executado",
        "sdk_mcp": importlib.metadata.version("mcp"),
        "transporte": "stdio (processo separado)",
        "rede": "nenhuma",
        "natureza": "real-local: SDK oficial, servidor e cliente locais; integração com o host não exercitada",
    })
    ok = (bool(res["protocolo_negociado"]) and (res["servidor"] or {}).get("nome") == "fundacao-ia-multiprojetos"
          and set(res["ferramentas"]) >= {"listar_projetos", "listar_documentos", "buscar"}
          and a.projeto in (res["projetos_visiveis"] or []) and a.outro not in (res["projetos_visiveis"] or [])
          and not res["chamada_autorizada"]["erro"] and res["negativa_outro_projeto"]["erro"]
          and "acesso negado" in res["negativa_outro_projeto"]["mensagem"] and res["encerrado"])
    res["verificacoes_ok"] = ok
    texto = json.dumps(res, ensure_ascii=False, indent=2)
    if a.saida:
        a.saida.parent.mkdir(parents=True, exist_ok=True)
        a.saida.write_text(texto, encoding="utf-8")
    print(texto)
    return 0 if ok else 1


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
