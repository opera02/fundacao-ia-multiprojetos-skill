"""Apoio às regressões da auditoria externa da 1.3.4 (só biblioteca padrão; nada do kit).

Ligações de diretório: junção no Windows (`mklink /J`, sem administrador) e link simbólico
nos demais sistemas. Link simbólico de ARQUIVO no Windows exige modo de desenvolvedor ou
administrador: sem ele, o teste que depende disso é pulado e o motivo fica no relatório.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


def criar_ligacao_dir(link: Path, alvo: Path) -> str:
    """Cria `link` apontando para o diretório `alvo` e devolve o tipo criado."""
    if os.name == "nt":
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(alvo)],
                           capture_output=True, text=True, errors="replace")
        if r.returncode != 0:
            raise unittest.SkipTest(f"junção indisponível neste ambiente: {r.stdout.strip()} {r.stderr.strip()}")
        return "juncao"
    try:
        link.symlink_to(alvo, target_is_directory=True)
    except OSError as exc:
        raise unittest.SkipTest(f"link simbólico indisponível neste ambiente: {exc}") from None
    return "link-simbolico"


def criar_link_arquivo(link: Path, alvo: Path) -> None:
    try:
        link.symlink_to(alvo)
    except (OSError, NotImplementedError) as exc:
        raise unittest.SkipTest(f"link simbólico de arquivo indisponível neste ambiente: {exc}") from None


def trocar_pasta_por_ligacao(pasta: Path, alvo: Path) -> str:
    """Guarda `pasta` ao lado (sufixo .original) e põe no lugar uma ligação para `alvo`."""
    pasta.rename(pasta.with_name(pasta.name + ".original"))
    return criar_ligacao_dir(pasta, alvo)


class _ToolErrorDeEnsaio(Exception):
    pass


class _ServidorDeEnsaio:
    """Dublê só do registro de ferramentas do SDK MCP (usado quando o pacote `mcp` falta)."""

    def __init__(self, *args, **kwargs):
        self.tools = {}

    def tool(self):
        def registrar(funcao):
            self.tools[funcao.__name__] = funcao
            return funcao
        return registrar


def chamar_ferramenta_mcp(root: Path, principal: str, ferramenta: str, argumentos: dict) -> tuple[bool, str, str]:
    """Chama uma ferramenta do servidor MCP da fundação e devolve (erro?, texto, modo).

    Com o SDK `mcp` instalado: cliente em processo do SDK real (transporte em memória).
    Sem ele: dublê do registro de ferramentas; a função da ferramenta e a política são as reais.
    """
    from fundacao.mcp_servidor import criar_servidor
    with mock.patch.dict(os.environ, {"FUNDACAO_PRINCIPAL": principal}):
        try:
            from mcp import Client  # noqa: F401
        except ImportError:
            modulos = {nome: types.ModuleType(nome) for nome in (
                "mcp", "mcp.server", "mcp.server.mcpserver", "mcp.server.mcpserver.exceptions")}
            modulos["mcp.server"].MCPServer = _ServidorDeEnsaio
            modulos["mcp.server.mcpserver.exceptions"].ToolError = _ToolErrorDeEnsaio
            with mock.patch.dict(sys.modules, modulos):
                app = criar_servidor(root)
                try:
                    resultado = app.tools[ferramenta](**argumentos)
                except _ToolErrorDeEnsaio as exc:
                    return True, str(exc), "duble-do-registro-mcp"
                return False, json.dumps(resultado, ensure_ascii=False), "duble-do-registro-mcp"
        from mcp import Client
        app = criar_servidor(root)

        async def roteiro():
            async with Client(app) as client:
                return await client.call_tool(ferramenta, argumentos)

        r = asyncio.run(roteiro())
        return bool(r.is_error), " ".join(getattr(c, "text", "") for c in r.content), "sdk-mcp-real"
