# Fontes verificadas e fatos voláteis

## Conferência da 1.7.10.1 — 02/11/2026
Duas fontes: o binário do Claude Code 2.1.302 fixado no Ubuntu (SHA-256 `60d7eb7f…e29a5`, o mesmo do relatório do
canário), lido sem executar, e as transcrições das 12 sessões do canário real de 02/11/2026 (`claude -p`, forma
`drvfs:/mnt/e`), lidas pelo coordenador. Valem para esta versão do Claude Code.

| Fato | Uso na fundação | Situação |
|---|---|---|
| O binário registra plugins embutidos na partida (`builtinPluginsInitialized`), qualquer que seja o `--setting-sources` e sem `--plugin-dir`: `cc-plugin-sec-default`, `cc-plugin-agents-md` e `cc-plugin-telemetry` sempre; `cc-plugin-plugin-authoring` e `cc-plugin-mods-guide` fora do ponto de entrada `local-agent`; outros (`tips`, `mermaid`, `responsive-mode`) sob condição. O `cc-plugin-agents-md` depende da opção remota `tengu_agents_md_mod` (ligada por padrão) e lê arquivos `AGENTS.md` como instrução (de projeto, local e de usuário) | **corrige** a linha da carga de plugins de 01/11/2026 ("nenhuma origem embutida"): a documentação não os cita, mas o binário os tem. Nas 12 sessões do canário, o `system/init` listou `cc-plugin-agents-md`, `cc-plugin-telemetry` e `cc-plugin-plugin-authoring`, com e sem `--plugin-dir`: o item `plugin_setting_sources_local` falhou por eles. A lista de embutidos do canário segue vazia (falha fechada) até a 1.7.11 decidir a lista por versão e conferir se o `AGENTS.md` lido por esse plugin respeita o `claudeMdExcludes` de `projects/*/data/**` | lido no binário (02/11/2026); a origem embutida, confirmada pelo `system/init` das sessões |
| No modo `-p`, um comando do Bash com variável (o `$?` do marcador `FIM-<nonce>-<i>-$?` do canário) é recusado antes de rodar, com "A variable in this command can't be checked before it runs" | das 29 chamadas do Bash do canário de 02/11/2026, 28 foram recusadas assim, também o controle do `/usr/bin/python3`, e 1 foi negada pelo `guarda_identidade.py`: os 7 itens de comando e a carga aninhada ficaram `nao_medido` sem nenhum comando rodar. A forma das sondas muda na 1.7.11 | visto nas transcrições (02/11/2026) |
| Numa das 12 sessões, a salvaguarda do modelo padrão da conta (Opus 5.5) parou a resposta e a sessão passou ao Opus 4.8, que se recusou a rodar o comando que montava o caminho de outro projeto por partes; o `guarda_identidade.py` negou o caminho escrito por inteiro | o canário depende do modelo aceitar rodar os comandos como estão: registrar o modelo de cada sessão e contar a recusa como `nao_medido` com motivo próprio (1.7.11) | visto nas transcrições (02/11/2026) |
| Sem nenhum comando rodar, o sandbox deixou na pasta do projeto do ensaio marcadores de 0 byte: `.env` e sete variantes, `.gitmodules`, `.npmrc`, `.yarnrc`, `.yarnrc.yml`, `bunfig.toml`, `package.json`, `package-lock.json`, `pnpm-lock.yaml` e `yarn.lock` | a lista de limpeza do lançador tem só `.npmrc`, `.yarnrc` e `.yarnrc.yml` além da obrigatória: ampliar na 1.7.11 | visto no relatório do canário (02/11/2026) |

## Conferência da 1.7.10 — 31/10 e 01/11/2026
Três fontes, cada uma com o seu limite:
- **Binário do Claude Code 2.1.302 instalado, lido sem executar:** busca de texto nos bytes do executável, sem abrir
  sessão. Lido pelos pacotes da 1.7.10 em 31/10/2026 e reconferido em 01/11/2026. É código minificado: o que vale aqui
  vale para a versão fixada, e uma versão nova pede leitura nova. Os nomes que os comentários do código citam para as
  duas varreduras da menção e para a expressão do cabeçalho são os do binário minificado desta versão no Ubuntu; no
  binário do Windows da mesma 2.1.302, esses nomes são outros (conferido em 01/11/2026). Vale o comportamento descrito
  abaixo, não o nome.
- **Páginas oficiais:** as de 31/10/2026 vieram pelo WebFetch, que resume a página com um modelo; antes de citar uma
  frase numa decisão assinada, confira-a de novo na página. A referência de carga de plugins foi lida em 01/11/2026.
- **Sondas de 31/10/2026**, com dados fictícios (`references/seguranca-isolamento.md` §8.1), e o que só o
  **canário** confirma no ambiente real, com o perfil do projeto (lista no fim desta seção).

**Binário 2.1.302 (lido sem executar)**

| Fato | Uso na fundação | Situação |
|---|---|---|
| O cabeçalho de skill, agente e comando é lido por `Bun.YAML.parse`, com o bloco cru: CR sozinho e os separadores U+2028 e U+2029 podem virar quebra de linha e mostrar uma chave que um leitor que só quebra no LF não vê | o plugin candidato recusa CR sozinho, U+2028 e U+2029 e quebra o cabeçalho em toda quebra (capacidade 08 §5) | lido (31/10 e 01/11/2026) |
| O binário conhece mais chaves de cabeçalho do que as listas positivas do plugin candidato aceitam; ficam de fora delas, por exemplo, `arguments`, `shell`, `hooks`, `mcpServers`, `lspServers`, `settings`, `permissionMode`, `initialPrompt`, `memory`, `background` e `isolation` | a lista positiva recusa o que não conhece; aceitar uma chave a mais é decisão de lista, com teste | lido |
| O shell embutido roda pelo bloco cercado aberto por três crases e `!`, sem âncora de começo de linha, e por `!` seguido de crase depois de espaço ou no começo da linha | o plugin candidato recusa os dois em qualquer ponto de qualquer Markdown | lido |
| Existe a configuração `disableSkillShellExecution`; com ela, o comando sai trocado por `[shell command execution disabled by policy]` | não está nos perfis da 1.7.10 | lido; não usado |
| A menção `@` de uma skill ou de um comando sai de duas varreduras independentes, somadas: (1) a forma entre aspas duplas (`@"..."`), no começo do texto ou depois de espaço ou de U+3002, U+3001, U+FF1F e U+FF01 (pontuação chinesa e japonesa), que cruza quebra de linha; (2) cada trecho sem espaço, com a primeira `@` do começo dele ou logo depois daquela pontuação, até o fim do trecho, sem os caracteres do fim que não são letra ASCII, número nem `_`. Da segunda, o alvo que começa com aspa dupla é descartado; aspas simples não têm tratamento; o `#L10-20` do fim é tirado antes de abrir o arquivo. O espaço é o do JavaScript, que inclui o U+FEFF | o kit (`aberturas_markdown`) colhe as duas, cada uma à parte, mais uma varredura larga, e recusa o alvo para fora; um teste diferencial prende isso contra uma transcrição da leitura (`assets/fundacao-kit/tests/test_aberturas_plugins_i16.py`; capacidade 08 §5) | lido (01/11/2026, revisão da integração; no binário do Ubuntu e no do Windows) |
| Ao invocar a skill ou o comando, o `getPromptForCommand` troca os argumentos (`$ARGUMENTS`, `$1`, `$ARGUMENTS[0]`, `$nome`) e as variáveis (`${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PROJECT_DIR}`, `${CLAUDE_PLUGIN_DATA}` e, depois, `${CLAUDE_SKILL_DIR}`) e só então colhe as menções `@` do texto expandido; o `allowed-tools` passa pela mesma troca | o validador do kit e o plugin candidato recusam `$` em qualquer ponto do alvo da menção e do especificador (capacidade 08 §5); o argumento da invocação pode trazer uma menção inteira, que nenhuma conferência do arquivo vê: limite, com a negação de leitura do perfil como barreira, a conferir no canário | lido (01/11/2026, reconferência da integração; a ordem das trocas, também no binário do Windows) |
| A leitura do cabeçalho tira uma marca U+FEFF (BOM) do começo, só uma, e então o cabeçalho sai do texto com `/^---\s*\n([\s\S]*?)---\s*\n?/`: abre só no começo do arquivo e fecha no primeiro `---` em qualquer ponto, também recuado ou no meio de uma linha | o kit e o plugin candidato tiram só o BOM do começo, recusam o de outro ponto (emenda E8) e conferem até a primeira linha `---`, o que contém o cabeçalho que o Claude Code lê (mais estrito) | lido (01/11/2026, reconferência da integração; no binário do Ubuntu e no do Windows) |
| Nome de plugin de terceiro: a mensagem do binário diz que ele não pode começar com certos prefixos, ser certos nomes nem pôr "official" ao lado de "claude" ou "anthropic"; perto dela estão `anthropics`, `cc-plugin` e `claude-mods`. A revisão do pacote leu os prefixos `claude-`, `anthropic-`, `anthropics-` e `cc-plugin-` e os nomes `claude-code` e `claude-mods`, sem reproduzir a normalização | o plugin candidato avisa, sem recusar, nome fora do kebab-case ou que cite `claude`, `anthropic` ou `cc-plugin` | lido; a carga de `<p>-<n>`, só no canário |
| Plugins carregados de pasta (`--plugin-dir` e a variável `CLAUDE_CODE_PLUGIN_DIRS`) são tratados como "inline" | o canário aceita o plugin do ensaio pelo nome ou pelo id `<nome>@inline` | lido; o campo do `system/init`, só no canário |
| As chaves `blockReadsOutsideWorkingDirectories`, `strictAllowlist`, `syncClaudeAiSkills` e `syncClaudeAiPlugins` existem | usadas no perfil do projeto (`references/seguranca-isolamento.md` §5) | lido |

**Páginas oficiais**

| Fato | Situação | Fonte |
|---|---|---|
| Padrões do sandbox: escrita só na pasta de trabalho, no temp por usuário (`$TMPDIR`) e nas pastas adicionadas, com os caminhos protegidos sempre negados; leitura de quase toda a máquina; não há lista de negação de credenciais embutida: só fica protegido o que for listado | novo (base do plano B do perfil) | code.claude.com/docs/en/sandboxing (31/10/2026) |
| Leitura com regras sobrepostas: vale o caminho mais estreito; `allowRead` reabre parte de um `denyRead`, e um `denyRead` exato continua negado dentro de um `allowRead` mais largo. Escrita: `denyWrite` bloqueia mesmo dentro de pasta gravável, e a biblioteca sandbox-runtime diz que `denyWrite` vence `allowWrite` | **corrige** a linha do §1 que dava essa precedência como não documentada | code.claude.com/docs/en/settings-reference; github.com/anthropic-experimental/sandbox-runtime (31/10/2026) |
| `Read(...)` em deny vira `denyRead` e `Edit(...)` em deny, `denyWrite`; a regra Read cobre as ferramentas de arquivo e os comandos que o Claude Code reconhece (`cat`, `head`, `sed`, redireções), não um subprocesso qualquer: este fica só com o sandbox | novo | code.claude.com/docs/en/settings-reference; /permissions (31/10/2026) |
| `permissions.blockReadsOutsideWorkingDirectories` (2.1.257+): Read, Grep, Glob e LSP recusam ler fora das pastas de trabalho; com o sandbox ligado, os comandos perdem a leitura da casa e de `/home`, `/root`, `/mnt`, `/media` e `/srv` | **conflito** com as sondas de 31/10/2026: com a pasta de trabalho em `/mnt/e`, os comandos listaram `/mnt/c` e `/mnt/d` e gravaram fora do projeto fictício (causa não conferida); só o canário decide | code.claude.com/docs/en/settings-reference (31/10/2026) |
| No Linux, o bwrap nega um caminho que não existe criando um arquivo vazio ou uma pasta vazia no lugar; somem no fim normal e ficam se o processo morre sem evento de saída | confirma o observado (marcadores de 0 byte); o lançador os limpa | github.com/anthropic-experimental/sandbox-runtime (31/10/2026) |
| As transcrições (`~/.claude/projects/...`), o histórico e o `file-history/` ficam em texto puro; `CLAUDE_CONFIG_DIR` leva todos os caminhos de `~/.claude` para outra pasta | novo (por isso o `CLAUDE_CONFIG_DIR` por projeto) | code.claude.com/docs/en/claude-directory; /env-vars (31/10/2026) |
| `allowedDomains` aceita domínio e `*.exemplo.com` (que não casa o próprio domínio); `strictAllowlist` (2.1.219) nega o host fora da lista em vez de perguntar | novo; o curinga na 2.1.302, medido no canário | code.claude.com/docs/en/settings-reference (31/10/2026) |
| O WebFetch roda dentro do processo do Claude Code, fora do sandbox, e não lê `allowedDomains`; `WebFetch(domain:x)` em `allow` libera `x` também para o sandbox; há domínios de documentação pré-aprovados; `CLAUDE_CODE_DISABLE_WEB_FETCH=1` desliga a ferramenta (2.1.285+) | novo (por isso `webfetch.dominios` contido em `rede.dominios` e o `guarda_rede.py` que nega sem perguntar) | code.claude.com/docs/en/permissions; /tools-reference (31/10/2026) |
| `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` tira credenciais do ambiente do Bash, dos hooks e dos servidores MCP; no Linux, o Bash roda num namespace de PID próprio | novo (no `env` do perfil do projeto) | code.claude.com/docs/en/env-vars (31/10/2026) |
| Sockets Unix: `allowUnixSockets` é ignorado no Linux e no WSL2; o filtro seccomp é opcional, e sem ele "sockets are unrestricted" | novo (por isso o perfil nega a leitura dos lugares de socket e o filtro só com `--seccomp-versao`) | code.claude.com/docs/en/sandboxing (31/10/2026) |
| Rodam fora do sandbox, com o acesso total do usuário: hooks de comando, servidores MCP locais, monitores de plugin, servidores LSP, linha de status, comandos digitados com `!`, comandos excluídos, novas tentativas sem sandbox e processos iniciados por mods | novo (por isso plugin com hooks, MCP ou monitor só na 1.7.11) | code.claude.com/docs/en/sandboxing; /plugins/mods/overview (31/10/2026) |
| Mods (2.1.287+, ligados por padrão) rodam dentro do Claude Code, sem sandbox; sem managed settings na máquina, um mod pode aprovar uma chamada que uma regra deny recusa ou que um hook bloqueou | novo (os hooks são guarda-corpos) | code.claude.com/docs/en/plugins/mods/overview (31/10/2026) |
| Managed settings: `/etc/claude-code/managed-settings.json` no Linux e no WSL, acima do `--settings`; "On WSL, /etc/claude-code is user-writable as well" | novo (por isso o preparo os fixa pelo SHA-256 e o lançador recusa os que aparecem depois) | code.claude.com/docs/en/managed-settings (31/10/2026) |
| `Skill(<nome>)` em deny nega a skill; desde a 2.1.260, o nome sem qualificação também bloqueia a skill aninhada qualificada; uma regra `allow` não abre exceção numa negação | novo (negações que acumulam) | code.claude.com/docs/en/skills; /permissions (31/10/2026) |
| `--setting-sources local` carrega só o `CLAUDE.local.md` e o `settings.local.json`; managed, `~/.claude.json` e a memória automática são lidos sempre; `syncClaudeAiSkills` e `syncClaudeAiPlugins` falsos valem de `--settings`, e `disableClaudeAiConnectors` de qualquer escopo | novo (base do lançador) | code.claude.com/docs/en/agent-sdk/claude-code-features; /settings; /mcp (31/10/2026) |
| `--settings` (até 2 MiB) fica acima de usuário, projeto e local, abaixo de managed; `--strict-mcp-config` usa só os servidores de `--mcp-config`; `--plugin-dir` carrega um plugin só naquela sessão | novo | code.claude.com/docs/en/cli-reference; /settings-reference (31/10/2026) |
| Carga de plugins: as origens são `@<marketplace>`, `@inline` (`--plugin-dir`, `--plugin-url`, `CLAUDE_CODE_PLUGIN_DIRS`), `@skills-dir` e `@synced`; plugin sincronizado não carrega numa sessão com `--setting-sources` sem `user`; nenhuma origem embutida. A referência do manifesto e o índice da documentação, também consultados, não citam plugin embutido | novo (lista de embutidos do canário vazia: plugin a mais no `system/init` falha fechado) | code.claude.com/docs/en/plugins/loading (01/11/2026); /plugins-reference; code.claude.com/docs/llms.txt |

**Só o canário confirma, na versão fixada e no ambiente real** (relatório `fundacao.ensaio_isolamento/1`;
`references/seguranca-isolamento.md` §8.4):
- que o perfil confina os comandos na forma de caminho da raiz (`/mnt/e` ou ext4) — o centro da 1.7.10;
- se o sandbox usa o `TMPDIR` do lançador; se negar `/tmp` e `/run` atrapalha o proxy do sandbox; o custo dos globs
  de `denyRead` em `/mnt`;
- se `Read(./**/X)` cobre o `X` da raiz do projeto, e se as regras Read filtram o resultado do Grep e do Glob (o
  `guarda_leitura.py` supõe o comportamento do ripgrep);
- se o matcher `*` pega toda ferramenta, e qual nome a 2.1.302 aceita no `--tools` (`Task` ou `Agent`);
- se o `--plugin-dir` carrega com `--setting-sources local`, com que id o plugin aparece no `system/init`, se o
  `Skill(<nome>)` negado bloqueia `<p>-<n>:<nome>` e se `projects/<p>/.claude/` deixa de carregar;
- se as chaves de cabeçalho fora da lista e o contexto dinâmico se comportam como a documentação diz; e, sem item no
  ensaio ainda, se a menção `@arquivo`, também a que chega pelo argumento da invocação (`$ARGUMENTS`), respeita as
  negações de leitura, e se uma linha do cabeçalho começada por tab fica fora das chaves de primeiro nível (a revisão
  da integração leu que sim, sem executar o leitor de YAML);
- a carga de skill ou agente aninhado (a descoberta pode ser dinâmica e ficar `nao_medido`);
- onde fica o login com `CLAUDE_CONFIG_DIR` (o ensaio espera `<config>/.credentials.json`) e quais são os campos do
  `system/init` do stream-json (skills, agentes, plugins, servidores MCP, ferramentas);
- a lista de marcadores de 0 byte (`.npmrc`, `.yarnrc`, `.yarnrc.yml`, `.env*`), os arquivos do filtro seccomp
  instalado sem os scripts do pacote, o retrato do shell (shell-snapshot) com `~/.local/share/fundacao-ia/**` negado e
  se o Bash lê a cópia da skill na área do titular, que a Read não lê.

## Conferência adicional da 1.7.9 — 22/10/2026

| Fato | Limite da conclusão | Fonte oficial |
|---|---|---|
| Claude Code aceita modelo e esforço explícitos por CLI; aliases e limites da organização podem mudar o resultado efetivo. | Registrar pedido e observado separadamente; flags não comprovam o modelo que respondeu. | [Configuração](https://code.claude.com/docs/en/model-config) |
| O limite financeiro do modo print usa estimativa do cliente e pode ser ultrapassado por uma chamada. | Não garantir fatura máxima; manter margem, teto de partidas e reconciliação. | [CLI](https://code.claude.com/docs/en/cli-reference) |
| Fable usa cota ou créditos conforme plano e limite disponível. | Acesso ao modelo não comprova gratuidade nem autoriza consumo. | [Fable no plano](https://support.claude.com/en/articles/15424964-claude-fable-models-on-your-plan) |

Esta leitura não consultou saldo, credenciais nem permissões da conta. O preparo
da 1.7.9 não fez chamada a provedor nem habilitou uma rota.

Data da conferência: **18/10/2026** (mesma data das referências do livro 2.0 e da
proposta 3.0). Conferência feita por leitura das páginas oficiais nesta data; reconfira
antes de instalar, atualizar, autenticar ou gastar. Situação: **confirma** o livro/3.0 ·
**corrige** (contradiz) · **conflito** entre fontes oficiais · **não verificado**.
Janela de atualidade declarada: 3 meses (metadados da skill).

## Sumário
1 Anthropic / Claude Code · 2 OpenAI / Codex · 3 MCP · 4 Agent Skills · 5 CAG e KV cache
· 6 SQLite e Python · 7 Segurança · 8 Itens do livro/3.0 não verificados · 9 Windows e WSL (host)
· 10 GitHub (CI pública)

## 1. Anthropic / Claude Code
| Fato | Situação | Fonte |
|---|---|---|
| Skills em `~/.claude/skills/<nome>/SKILL.md`, `.claude/skills/<nome>/`, plugins; `~/.agents/skills` **não** é lido pelo Claude Code (use cópia ou link) | confirma; complementa | code.claude.com/docs/en/skills |
| Campos extras ignorados sem erro; listagem trunca descrição + `when_to_use` em 1.536 caracteres; mudanças valem na sessão (nova pasta raiz: `/reload-skills`; renomear: reiniciar) | novo | code.claude.com/docs/en/skills |
| PreToolUse: `hookSpecificOutput.permissionDecision` allow/deny/ask/defer + `permissionDecisionReason`; `decision`/`reason` no topo depreciados; código 2 bloqueia | confirma 3.0 | code.claude.com/docs/en/hooks |
| Matcher `A\|B` exato; outros caracteres = regex; MCP `mcp__<servidor>__.*`; `MultiEdit` legado. [21/10/2026] `*`, vazio ou ausente = tudo; só letras, dígitos, `_`, `-`, espaço, `,` e `\|` = lista exata (`A\|B` ou `A, B`); outro caractere = expressão regular de JavaScript sem âncora (a alternativa vazia de `a \|\| b` casa tudo); `mcp__memory` sozinho não casa nada; ferramenta de servidor de plugin: `mcp__plugin_<plugin>_<servidor>__<ferramenta>`; evento sem matcher (UserPromptSubmit, Stop e outros) ignora o campo; os nomes de ferramenta estão na referência de ferramentas | complementa 3.0 R4.2 | code.claude.com/docs/en/hooks; /tools-reference |
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
| Plugins: `plugin.json` (só `name` obrigatório); `claude plugin validate [--strict]`; `marketplace.json` exige `name`, `owner`, `plugins`; `claude plugin install\|enable\|disable\|uninstall --scope user\|project\|local`; `${CLAUDE_PLUGIN_ROOT}`. [21/10/2026] No disco, em `~/.claude/plugins/`: `installed_plugins.json` (`installPath`, `scope`, `version`), `cache/<catálogo>/<plugin>/<versão>/` e `synced/` (plugins do claude.ai, id `<nome>@synced`, sem registro de instalação); hooks em `hooks/hooks.json` (com a chave `hooks`) e no campo `hooks` do manifesto (caminho, objeto ou lista); MCP em `.mcp.json` e `mcpServers`; skills em `skills/` e no campo `skills`; caminho de componente que sai da pasta do plugin, inclusive por ligação, não carrega | confirma; novo | code.claude.com/docs/en/plugins/...; /plugins/loading; /plugins-reference |
| Subagentes `.claude/agents/<nome>.md` (`name`, `description`; `tools`, `model` opcionais); consomem os mesmos limites | confirma | code.claude.com/docs/en/sub-agents |
| `claude mcp add --scope project` → `.mcp.json`; escopos local (padrão), project, user | confirma 3.0 | code.claude.com/docs/en/mcp |
| Sandbox no Linux e no WSL2: depende de `bubblewrap` e `socat` (`sudo apt-get install bubblewrap socat`); no Ubuntu 24.04 ou mais novo, com `kernel.apparmor_restrict_unprivileged_userns` = 1, perfil do AppArmor para o `bwrap` (`/etc/apparmor.d/bwrap`, `userns`) e `sudo systemctl reload apparmor`; no WSL2, abrir programa do Windows passa por socket Unix, que só o filtro seccomp opcional bloqueia | novo (base do `assets/host/wsl/preparar-wsl.sh`) | code.claude.com/docs/en/sandboxing (conferido em 2026-10-21) |
| Caminhos do sandbox: `/abs` e `~/` (as regras Read/Edit usam `//` para absoluto); `allowRead` reabre leitura dentro de `denyRead` (o caminho mais estreito vale); fonte excluída por `--setting-sources` não entra no sandbox (v2.1.246+); a precedência entre `allowWrite` e `denyWrite` sobrepostos não estava documentada, por isso o perfil nega os outros projetos um a um [31/10/2026: `denyWrite` vence; conferência da 1.7.10] | novo (base do `assets/host/wsl/settings.wsl.json`) | code.claude.com/docs/en/sandboxing (conferido em 2026-10-21) |
| Observado na implantação real (2.1.302): `Read(./state/**)` em `permissions.deny` também nega a leitura no sandbox, e `state/` aparece vazio e gravável (tmpfs) até ganhar `allowRead` e `allowWrite` (perfis v1 a v3) | executado | implantação de referência, 2026-10-20 |
| Observado no Claude Code 2.1.304 (Ubuntu/WSL, sandbox ligado): antes de cada comando de shell, a CLI cria `.claude/.cc-writes` (modo 700; `.claude`, se faltar, com o modo padrão) na pasta em que a sessão começou, na raiz do projeto e no diretório atual do shell; depois de um `cd`, também na pasta nova. Pelo código da CLI, o diretório acompanhado vem de `pwd -P` no fim do comando (comando que falha não o muda), e um `cd` dentro de subshell `( … )` não o muda (regra do POSIX; não observado numa sessão). Auditoria somente leitura que muda o diretório para dentro da árvore a altera; sessão aberta dentro da árvore ganha a pasta na raiz dela sem nenhum `cd` | executado (sessões com dados fictícios) e lido no código | binário da CLI 2.1.304 (`ensureAtomicWriteStagingDirs`), 2026-10-25 |
| CLI: `claude "consulta"` abre a sessão interativa com essa primeira mensagem; `--settings <arquivo>` sobrepõe as chaves dos settings; `--setting-sources user,project,local` escolhe as fontes | confirma | code.claude.com/docs/en/cli-reference (conferido em 2026-10-21) |
| Instalação nativa no Linux: `~/.local/bin/claude` é ligação para `~/.local/share/claude/versions/<versão>`; o instalador guarda a versão do lançador, as que estão rodando e as duas mais novas e apaga as outras; `DISABLE_AUTOUPDATER=1` só para a verificação em segundo plano (`DISABLE_UPDATES` bloqueia todas) | novo (por isso o `preparar-wsl.sh` copia a versão fixada para fora de `versions/`) | code.claude.com/docs/en/setup (conferido em 2026-10-21) |
| Integridade: `https://downloads.claude.ai/claude-code-releases/<versão>/manifest.json` traz o SHA-256 de cada binário em `platforms.<plataforma>.checksum` e é assinado em `manifest.json.sig` pela chave de lançamento `31DD DE24 DDFA B679 F42D 7BD2 BAA9 29FF 1A7E CACE` (desde a 2.1.89); no Linux o binário não tem assinatura própria. Na implantação de referência, a 2.1.302 linux-x64 = `60d7eb7f12fbb28a52533fe8be5884097403562aa02dc73991a021c7067e29a5`, conferido com a assinatura | confirma | code.claude.com/docs/en/setup; manifest.json da 2.1.302 (conferido em 2026-10-21) |
| Instruções [conferido em 21/10/2026]: o `CLAUDE.md` da pasta da sessão e das pastas acima carrega ao iniciar; os de subpastas, quando a sessão lê arquivos nelas; `@AGENTS.md` dentro do `CLAUDE.md` importa sem duplicar; o `AGENTS.md` sozinho só é lido direto quando não há `CLAUDE.md` (2.1.277 ou posterior); recomendação: menos de 200 linhas por arquivo; `claudeMdExcludes` (globs de caminho absoluto, em qualquer camada de configuração) impede que instruções de pastas carreguem | novo | code.claude.com/docs/en/memory |
| Skills em `.claude/skills/` de subpastas passam a valer na primeira leitura ou edição de arquivo ali, e nenhuma configuração desliga essa descoberta; `Skill(<nome>)` em `permissions.deny` nega a skill [21/10/2026] | novo | code.claude.com/docs/en/skills; code.claude.com/docs/en/permissions |
| `WebFetch` e `WebSearch` sem padrão em `permissions.deny` retiram a ferramenta da sessão; o sandbox cobre só os comandos de shell (Bash, PowerShell, Monitor), não ferramentas de arquivo, web nem MCP [21/10/2026] | novo | code.claude.com/docs/en/permissions; code.claude.com/docs/en/sandboxing |

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
| `AGENTS.md`: lido da raiz do Git até a pasta atual (sem Git, só a pasta atual), até 32 KiB somados [21/10/2026] | novo | learn.chatgpt.com/docs (AGENTS.md) |
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

## 9. Windows e WSL (host)
| Fato | Situação | Fonte |
|---|---|---|
| `/etc/wsl.conf`, seção `[interop]`: `enabled` (abrir programas do Windows) e `appendWindowsPath` (o PATH do Windows), ambos `true` por padrão; a mudança vale depois que a distribuição para (regra dos 8 segundos; `wsl --terminate <distribuição>` ou `wsl --shutdown`); `[automount] root` padrão `/mnt/` | confirma (base do `preparar-wsl.sh`) | learn.microsoft.com/en-us/windows/wsl/wsl-config (conferido em 2026-10-21) |
| Observado no Windows 11 26200 (2026-10-20 e 2026-10-21): arquivo criado por administrador elevado nasce com o próprio usuário como dono, e o dono tem `WRITE_DAC` implícito; `(OI)(CI)` aplicado a um arquivo o deixa sem permissões efetivas; na pasta ProgramData, Usuários criam pastas e arquivos (`(CI)(WD,AD)`) e o CREATOR OWNER ganha controle total no que criar, por isso a herança é cortada na pasta da âncora e na de cima | executado | `assets/host/windows/preparar-maquina.ps1`; implantação de referência |
| Observado no WSL2 (Ubuntu 24.04.5, kernel 6.6.87.2, bubblewrap 0.9.0, 2026-10-21): o `bwrap` abre sem perfil do AppArmor (o kernel do WSL não tem `apparmor_restrict_unprivileged_userns`); com `--unshare-all`, o sandbox só tem a interface `lo`; com as montagens do plano do `caracterizar.py`, `/home`, `/mnt` e as pastas não montadas não existem lá dentro; um `bwrap` dentro de outro (`/` só leitura, PIDs e rede próprios) também abre. Dentro do sandbox do Claude Code, que acrescenta um filtro seccomp, não foi conferido | executado | `scripts/tests/test_auditoria_1_7_6_execucao_isolada.py` rodado no WSL2 |

## 10. GitHub (CI pública)
| Fato | Situação | Fonte |
|---|---|---|
| GitHub Actions é gratuito em repositório público com runners padrão [21/10/2026] | novo | docs.github.com/en/billing/concepts/product-billing/github-actions |
| `actions/checkout` v7.0.1 = commit `3d3c42e5aac5ba805825da76410c181273ba90b1` e `actions/setup-python` v7.0.0 = commit `5fda3b95a4ea91299a34e894583c3862153e4b97`, ambas publicadas em 20/07/2026; tags leves (o SHA da tag é o do commit) | executado (`git ls-remote` e API de releases, 21/10/2026) | github.com/actions/checkout; github.com/actions/setup-python |
| `GET https://api.github.com/repos/<dono>/<repo>/actions/runs?head_sha=<commit>` responde sem credencial em repositório público, com `status`, `conclusion`, `path` e `html_url` de cada execução; limite de 60 pedidos por hora por IP (`X-RateLimit-Limit: 60`) | executado (21/10/2026) | docs.github.com/en/rest/actions/workflow-runs |
