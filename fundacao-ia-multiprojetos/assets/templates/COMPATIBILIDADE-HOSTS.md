# Quadro de compatibilidade por anfitrião (skills, hooks, MCP, plugins)

Estados permitidos: instalado e testado · adaptado e testado · documentação consultada · não verificado.
"Arquivo copiado" ≠ "componente descoberto" ≠ "executado" ≠ "validado".

| Componente | Anfitrião | Versão do anfitrião | Forma de instalação/escopo | Descoberta | Execução | Desativação | Estado | Evidência |
|---|---|---|---|---|---|---|---|---|
| skill comum | Claude Code | | `.claude/skills/<nome>/` (projeto) | | | | | |
| skill comum | Codex | | `.agents/skills/<nome>/` (repositório) | | | | | |
| hook PreToolUse | Claude Code | | `.claude/settings.local.json` | | | | | |
| hook PreToolUse | Codex | | `.codex/hooks.json` (projeto confiável) | | | | | |
| servidor MCP | Claude Code | | `claude mcp add --scope project` → `.mcp.json` | | | | | |
| servidor MCP | Codex | | `[mcp_servers.<nome>]` em `config.toml` | | | | | |
| plugin | Claude Code | | marketplace local + `claude plugin install --scope local` | | | | | |

Fonte canônica da skill/plugin: `components/` da fundação. Registre o hash de cada cópia distribuída.
