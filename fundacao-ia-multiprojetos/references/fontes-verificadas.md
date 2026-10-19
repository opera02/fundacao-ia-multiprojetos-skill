# Fontes verificadas e fatos voláteis

Data da conferência: **18/10/2026** (mesma data das referências do livro 2.0 e da
proposta 3.0). Conferência feita por leitura das páginas oficiais nesta data; reconfira
antes de instalar, atualizar, autenticar ou gastar. Situação: **confirma** o livro/3.0 ·
**corrige** (contradiz) · **conflito** entre fontes oficiais · **não verificado**.
Janela de atualidade declarada: 3 meses (metadados da skill).

## Sumário
1 Anthropic / Claude Code · 2 OpenAI / Codex · 3 MCP · 4 Agent Skills · 5 CAG e KV cache
· 6 SQLite e Python · 7 Segurança · 8 Itens do livro/3.0 não verificados

## 1. Anthropic / Claude Code
| Fato | Situação | Fonte |
|---|---|---|
| Skills em `~/.claude/skills/<nome>/SKILL.md`, `.claude/skills/<nome>/`, plugins; `~/.agents/skills` **não** é lido pelo Claude Code (use cópia ou link) | confirma; complementa | code.claude.com/docs/en/skills |
| Campos extras ignorados sem erro; listagem trunca descrição + `when_to_use` em 1.536 caracteres; mudanças valem na sessão (nova pasta raiz: `/reload-skills`; renomear: reiniciar) | novo | code.claude.com/docs/en/skills |
| PreToolUse: `hookSpecificOutput.permissionDecision` allow/deny/ask/defer + `permissionDecisionReason`; `decision`/`reason` no topo depreciados; código 2 bloqueia | confirma 3.0 | code.claude.com/docs/en/hooks |
| Matcher `A\|B` exato; outros caracteres = regex; MCP `mcp__<servidor>__.*`; `MultiEdit` legado | complementa 3.0 R4.2 | code.claude.com/docs/en/hooks |
| `if` existe (regra de permissão, melhor esforço, só eventos de ferramenta); `args` existe em hooks `command` (forma exec) | **corrige 3.0** (que não encontrou `args`) e confirma o livro | code.claude.com/docs/en/hooks |
| Regras de arquivo consultam só `Edit(...)` e `Read(...)`; `Write(...)` é aceito e nunca consultado | **corrige o livro** (exemplo `if: "Write(data/lab-hooks/**)"`, p57) | code.claude.com/docs/en/permissions |
| Timeout em segundos (padrão 600); PostToolUse não desfaz; `/hooks` só leitura; `disableAllHooks` | confirma | code.claude.com/docs/en/hooks |
| Permissões: deny → ask → allow; `Bash(ls *)` ≡ `Bash(ls:*)`; Bash não é fronteira | confirma | code.claude.com/docs/en/permissions |
| Windows nativo: comandos **sem sandbox**; WSL2 obrigatório para sandbox (WSL1 não); `sandbox.failIfUnavailable`; sandbox cobre só shell | confirma 3.0 | code.claude.com/docs/en/sandboxing |
| `claude -p --output-format json`: `result`, sessão, `total_cost_usd`, `usage`; conferir `is_error`; `--bare` não lê OAuth, ignora hooks/skills/plugins/MCP, exige chave; sem `--bare`, `-p` executa hooks e `.mcp.json` mesmo em pasta não confiável | confirma livro (E10); alerta novo | code.claude.com/docs/en/headless, /cli-reference |
| Isolar `claude -p` num processo de automação: `--tools ""` (sem ferramentas nativas; não afeta MCP), `--disallowedTools "mcp__*"` (remove ferramentas MCP), `--strict-mcp-config` (só servidores de `--mcp-config`), `--restricted` (v2.1.248+: sem ferramentas que executam comandos, ferramentas de arquivo confinadas à pasta de trabalho, só configurações gerenciadas e `--settings`), `--max-turns`, `--no-session-persistence`, `--permission-prompts none` (v2.1.259+), `--max-budget-usd` (estimativa do cliente; pode passar do teto), `--safe-mode` (desliga personalizações, mantém autenticação) | novo (base dos adaptadores do kit; não executado nesta entrega) | code.claude.com/docs/en/cli-reference (conferido em 18/10/2026) |
| Entrada padrão no modo não interativo: `cat arquivo \| claude -p 'consulta'` processa o conteúdo recebido (limite de 10 MB) | novo (base do adaptador: tarefa e dados pela entrada; não executado) | code.claude.com/docs/en/cli-reference, /headless (conferido em 18/10/2026) |
| Neste ambiente (observado, não documentação): `claude --help` da 2.1.302 lista `-p`, `--output-format`, `--tools`, `--disallowedTools`, `--strict-mcp-config`, `--restricted`, `--no-session-persistence`, `--permission-prompts` (host\|none) e `--max-budget-usd`; `--max-turns` não aparece no `--help`, mas a opção `--max-turns <turns>` consta do executável | executado (só `--help` e leitura do executável; nenhuma chamada de modelo) | `claude --help`; `~/.local/bin/claude` (18/10/2026) |
| OAuth da assinatura: uso comum do Claude Code; produtos/serviços (inclusive Agent SDK) usam chave de API | confirma 3.0 | code.claude.com/docs/en/legal-and-compliance |
| Créditos de API: Max 5x US$ 100/mês, Max 20x US$ 200/mês; Team por assento (teto US$ 500); Console vinculado; sem acúmulo; Pro/Enterprise inelegíveis; não usáveis no Claude Code/apps | confirma 3.0 | support.claude.com/en/articles/17154008; platform.claude.com/docs/en/about-claude/api-credits-for-subscribers; support.claude.com/en/articles/11145838 |
| Créditos cobrem `claude -p` **só com chave de API** da organização (FAQ) × sem essa condição (artigo 15036540, atualização 07/10/2026) | **conflito oficial** → confirmar na conta | support.claude.com/en/articles/15036540 |
| Prompt caching: `input_tokens` exclui cache; total = input + cache_creation + cache_read; TTL 5 min (1 h opcional); escrita 1,25×/2×, leitura 0,1× (alguns modelos menos); sem limpeza manual | confirma livro e 3.0 | platform.claude.com/docs/en/build-with-claude/prompt-caching |
| Plugins: `plugin.json` (só `name` obrigatório); `claude plugin validate [--strict]`; `marketplace.json` exige `name`, `owner`, `plugins`; `claude plugin install\|enable\|disable\|uninstall --scope user\|project\|local`; `${CLAUDE_PLUGIN_ROOT}` | confirma | code.claude.com/docs/en/plugins/... |
| Subagentes `.claude/agents/<nome>.md` (`name`, `description`; `tools`, `model` opcionais); consomem os mesmos limites | confirma | code.claude.com/docs/en/sub-agents |
| `claude mcp add --scope project` → `.mcp.json`; escopos local (padrão), project, user | confirma 3.0 | code.claude.com/docs/en/mcp |

## 2. OpenAI / Codex (páginas `developers.openai.com/codex/*` redirecionam para `learn.chatgpt.com/docs/*`)
| Fato | Situação | Fonte |
|---|---|---|
| `codex exec --json`: JSONL `thread.started`, `turn.started`, `turn.completed`, `turn.failed`, `item.*`, `error`; uso em `turn.completed.usage` (`input_tokens`, `cached_input_tokens`, `output_tokens`, `reasoning_output_tokens`) | confirma 3.0 | learn.chatgpt.com/docs/non-interactive-mode |
| `cached_input_tokens` contido em `input_tokens` | **não documentado**; inferido do código-fonte (protocol.rs) | github.com/openai/codex |
| Sandbox padrão do exec somente leitura; `--sandbox workspace-write\|danger-full-access`; `--skip-git-repo-check`; `-o/--output-last-message`; `--output-schema`; `--ephemeral`; `codex exec resume` | novo | learn.chatgpt.com/docs/non-interactive-mode |
| `codex exec --ephemeral` (não grava a sessão), `--ignore-user-config` (não carrega `$CODEX_HOME/config.toml`), `--ignore-rules` (ignora `.rules`); a página **não** documenta flag de pasta de trabalho nem diz se o modo somente leitura impede ler fora da pasta (trate como não isolado para leitura) | novo (base do adaptador do kit; não executado) | learn.chatgpt.com/docs/non-interactive-mode (conferido em 18/10/2026) |
| `--full-auto` **descontinuado** | novo | learn.chatgpt.com/docs/non-interactive-mode |
| Neste ambiente (observado): `codex exec --help` da 0.163.0 — "If not provided as an argument (or if `-` is used), instructions are read from stdin"; lista `--json`, `--sandbox read-only`, `--ephemeral`, `--ignore-user-config` ("auth still uses `CODEX_HOME`"), `--ignore-rules` e `--skip-git-repo-check` | executado (só `--help`; nenhuma chamada de modelo) | `codex exec --help` (18/10/2026) |
| Login ChatGPT (assinatura) ou chave de API (faturado); chave recomendada para automação/CI; `codex login status`; `CODEX_API_KEY` por invocação | confirma 3.0 | learn.chatgpt.com/docs/auth |
| Skills: `.agents/skills` (do diretório atual à raiz do repo), `~/.agents/skills`, `/etc/codex/skills`; `~/.codex/skills` só compatibilidade | confirma livro (E24) | learn.chatgpt.com/docs/build-skills |
| Hooks oficiais: `hooks.json` ou `[hooks]` no `config.toml` (`~/.codex/` ou `.codex/` confiável); PreToolUse/PostToolUse e outros; negação por `permissionDecision`; confiança por hash; proteção, não fronteira completa | **corrige 3.0** ("só fontes secundárias") | learn.chatgpt.com/docs/hooks |
| MCP no Codex: `[mcp_servers.<nome>]` (`command`, `args`, `env`, `cwd` / `url`), `codex mcp add\|list\|login` | confirma 3.0 | learn.chatgpt.com/docs/extend/mcp |

## 3. Model Context Protocol
| Fato | Situação | Fonte |
|---|---|---|
| Versão vigente **2026-07-28**; sem sessões/`Mcp-Session-Id`; sem `initialize`/`notifications/initialized`; versão e capacidades em `_meta` por requisição; servidores **devem** implementar `server/discover` (clientes podem chamar); `ping` e `logging/setLevel` removidos; Roots/Sampling/Logging/HTTP+SSE/DCR depreciados (≥ 12 meses); MRTR | confirma livro e 3.0 (ajuste: discover é obrigatório no servidor) | modelcontextprotocol.io/specification/versioning; /2026-07-28/changelog |
| SDK Python `mcp` 2.x estável; última 2.3.0 (02/10/2026); Python ≥ 3.10; `FastMCP` → `MCPServer` (`from mcp.server import MCPServer`; guia de migração usa `mcp.server.mcpserver`); `from mcp import Client` com `mode='auto'\|'legacy'\|'2026-07-28'`; 1.x só correções | confirma livro e 3.0 (atualiza versão) | pypi.org/project/mcp; py.sdk.modelcontextprotocol.io |
| Neste ambiente (observado): URI `file:` do SQLite para caminho de rede — `Path.as_uri()` de `\\localhost\C$\…` gera `file://localhost/…` e o SQLite responde "unable to open database file"; com o prefixo de caminho longo, "invalid uri authority". `file:////…` (autoridade vazia) abre nos dois casos | executado (`backup_sqlite.py` e CLI do kit; ensaio da 3ª conferência) | Python 3.12.10, SQLite 3.49.1 (18/10/2026) |
| Neste ambiente (observado): Job Object do Windows (`CreateJobObjectW` + `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` + `AssignProcessToJobObject`) criado e atribuído ao processo da CLI pelo Python (`ctypes`), mesmo com a sessão do Claude Code; `TerminateJobObject` encerra também o neto órfão | executado (`test_neto_orfao_nao_prende_nem_sobrevive`) | Windows 11 26200, Python 3.12.10 (19/10/2026) |
| Neste ambiente (observado, não documentação): SDK `mcp` 2.3.0 instalado; `Client(StdioServerParameters(...))` sobe o servidor em processo separado; erro deliberado da ferramenta (`ToolError`) chega ao cliente como `is_error=True` com mensagem curta; versão negociada (`client.protocol_version`) **2026-07-28** e servidor identificado (`client.server_info`) | executado (ensaio CEN-15) | `scripts/mcp_ensaio.py`; `assets/fundacao-kit/fundacao/mcp_servidor.py` |

## 4. Agent Skills (padrão aberto)
`name` 1–64 `a-z0-9-` igual à pasta; `description` 1–1.024 (o quê e quando);
opcionais `license`, `compatibility` (≤ 500), `metadata` (mapa de textos),
`allowed-tools` (experimental); corpo < 5.000 tokens / < 500 linhas; `scripts/`,
`references/`, `assets/`; `skills-ref validate` — **confirma 3.0** — agentskills.io/specification.

## 5. CAG e KV cache
| Fato | Situação | Fonte |
|---|---|---|
| Método: pré-carregar recursos, pré-computar KV, inferência sem recuperação, reset truncando a pergunta | confirma livro | arxiv.org/abs/2412.15605; github.com/hhhuang/CAG (`kvcache.py`) |
| Código dos autores usa API antiga do Transformers (`key_cache[i]`) | novo — fixar versão ou adaptar | github.com/hhhuang/CAG |
| Transformers v5: `DynamicCache` padrão; reutilização de prefixo com `copy.deepcopy`; `crop()`; sem guia oficial de salvar cache em disco | confirma livro; complementa | huggingface.co/docs/transformers/en/kv_cache |
| Observado nesta skill (transformers 5.10.2, torch 2.12 CPU, modelo sintético): bytes do KV = fórmula do livro (177.664 B para 347 tokens, 2 camadas, 2 cabeças KV, dim 16, fp32) | executado | `scripts/cag_kv_demo.py` |

## 6. SQLite e Python
FTS5: `unicode61` padrão; `remove_diacritics 2` desde 3.27.0; `bm25()` menor = melhor;
`secure-delete` do FTS5 desde 3.42.0 (sqlite.org/fts5.html). Python `sqlite3`:
`Connection.autocommit` desde 3.12 (padrão ainda legado), `backup(target, ...)`
(docs.python.org/3/library/sqlite3.html). Python no Windows: gerenciador `py`/`pymanager`;
sem runtime instalado, lançar `python` pode instalar o mais recente automaticamente
(docs.python.org/3/using/windows.html). Ambiente desta entrega: Python 3.12.10, SQLite
3.49.1 com FTS5 `unicode61 remove_diacritics 2` funcionando.

## 7. Segurança
OWASP Top 10 for Agentic Applications for 2026 (publicado 09/12/2025; ASI01–ASI10) e
LLM01:2025 Prompt Injection (direta e indireta; privilégio mínimo; aprovação humana;
segregar conteúdo externo) — genai.owasp.org.

## 8. Itens do livro/3.0 não verificados nesta skill
- Versões editoriais do livro (Python 3.12.14, SQLite 3.53.1) [Livro p210].
- Situação e números do Headroom; "agent teams"; Resolução CNJ 615/2025; governança do
  AGENTS.md; requisitos de peticionamento por tribunal; dispositivos do Código de Ética
  citados na 3.0; leis de software; Recomendação CFOAB 001/2024; Res. CD/ANPD 19/2024;
  PL 2.338/2023; configurações de treinamento por plano (Anthropic/OpenAI); dado de
  consumo de multiagentes (Anthropic, 2025) — todos citados pela proposta 3.0 e mantidos
  como **[3.0 — não verificado]** nas referências.
- Ferramentas recomendadas pela 3.0 (DBOS, docxtpl, promptfoo, uv, restic, Kopia,
  sqlite-vec, modelos de embedding) são **recomendações de engenharia**, não fatos;
  valide no protótipo antes de adotar [3.0 §9].
