# 08 — Ferramentas, hooks, MCP, skills e plugins (ciclo de vida completo)

Requisitos: R32–R36, R47 (e R52, R54 da 3.0). Aulas: A11 [Livro p52–55], A11B
[p56–59], A11C [p60–63], A11D [p64–67], A11E [p68–71], A34 [p170–173]; 3.0 §3.4.
Ordem recomendada [3.0 R4.18]: componentes → skills → hooks/permissões → MCP → plugins.

## Sumário
1 Componentes e registro · 2 Hooks · 3 MCP · 4 Skills · 5 Plugins · 6 Quando usar o quê

## 1. Componentes e registro (R32, R47) [Livro A11]
Descoberta (saber que existe) · instalação (arquivos e dependências) · ativação
(autorizado a participar) · saúde (consegue operar agora) · autorização (esta tarefa
pode usar) — estados distintos [Livro p52, p170]. Registro próprio (contrato da
fundação, não formato nativo): `schema_version`, `component_id`, `version`,
`entrypoint`, permissões, projetos autorizados, timeout, estado, evidências; consulte
`enabled` **antes** de importar ou iniciar; descobrir não executa [Livro p53].
Componente em subprocesso com timeout real [3.0 R2.6]; no kit, a descoberta não importa o
pacote pai das dependências e o timeout encerra a árvore de processos [auditoria sobre a
1.4.1, A06/A08; varredura da 1.4.5, #25]. Ciclo: interface → implementação
→ instalação documentada → descoberta sem execução → habilitar e demonstrar nos dois
projetos → desabilitar (contador de chamadas prova que o ponto de entrada não foi
atingido) → atualizar em separado (0.1.0 → 0.2.0 com campo opcional) → voltar à versão
anterior preservando evidências [Livro p53–54]. Desligar deve valer por **todas** as
rotas (MCP, plugin, hook, fila, agendador) [Livro p55]. Modelo:
`assets/templates/INVENTARIO-COMPONENTE.json`. Kit: `fundacao/core/components.py` (tetos:
`fundacao/core/limites.py`; testes do teto: `tests/test_auditoria_1_7_6_recursos.py`).
[Decisão; auditoria externa da 1.3.4] No kit, o despacho aceita só o registro confiável: ID
validado antes de montar caminho, arquivo de `registry/components/<id>.json` (contido no
registro) que declare o mesmo `component_id`, ponto de entrada em `fundacao.components.<modulo>`
e, se a habilitação gravou `entrypoint_sha256`, o mesmo código aprovado. Componente lido pelo
host (`entrypoint: "host-skill:<caminho do SKILL.md>"`) não é executado pelo kit; desabilitá-lo no
registro **não** o desliga no host, e o comando avisa enquanto o arquivo existir (ver §4).
[Decisão; auditoria Codex Security da 1.7.6, #9] **Teto de recursos por componente.** Prazo e
autorização não limitam memória: um filho escreve gigabytes antes do prazo. O registro pode declarar
`limits` — `request_bytes` (pedido serializado), `stdout_bytes` (o resultado em JSON), `stderr_bytes`,
`max_files`, `file_bytes` e `total_file_bytes`; o que não declara vale pelo padrão (1 MiB, 4 MiB, 1 MiB,
1000, 1 GiB e 4 GiB; `assets/fundacao-kit/fundacao/core/limites.py`). Nome desconhecido ou valor que não
seja inteiro positivo torna o registro inválido. Pedido acima do teto é recusado antes de iniciar o
processo (`E_LIMITE_EXCEDIDO`; despacho `denied_limit`). stdout ou stderr acima do teto: o executor
(`assets/fundacao-kit/fundacao/core/processo.py`) lê em blocos, encerra a árvore na hora e registra
`component_limit`. Os tetos de arquivo vão no pedido: o `source_manifest` 0.2.0 recusa identificadores
demais antes de ler, lê o repetido uma vez e recusa pelo tamanho no disco, sem abrir, o arquivo acima do
teto ou que passaria do teto somado; a leitura é em blocos. Habilitar e desabilitar regravam o registro
pela publicação segura (#11; `references/seguranca-isolamento.md` §2). Limite: a memória do próprio
processo do componente não tem teto do sistema.
**Ecossistema do host** (R54) [Decisão; 1.7.0]: `python <skill>/scripts/inventariar_host.py gravar --saida
<raiz>/registry/inventario-host.json --raiz <raiz>` registra, só lendo e sem rede, as skills do perfil e da raiz
(ligação, `name`, versão, SHA-256, primeira linha da licença e nomes repetidos em pastas diferentes), plugins (id,
versão, escopo e se há projeto, sem o caminho dele, que pode trazer nome de cliente), catálogos, hooks e servidores
MCP — destes, só nome, tipo, o nome do executável (nunca caminho nem argumentos, mesmo num `command` em texto único,
que pode trazer token; o que não tem forma de nome, como `$env:NOME='valor';`, sai nulo [Decisão; revisão de
segurança da 1.7.7, R177-VAL-05]) ou o host da URL (URL malformada: host nulo); nunca `env`, `headers` nem dados da
conta. O `atualizar_fundacao.py aplicar` termina com `verificar`, sem bloquear.
**Plugins por dentro** [Decisão; everything-claude-code, proposta 1]: no esquema `fundacao.inventario-host/2`, o
inventário lê também o que cada plugin carrega (`scripts/inventario_plugins.py`). Lê só dentro de `~/.claude/plugins/`:
o `installPath` de cada instalação e as pastas de `synced/` (plugins sincronizados do claude.ai). Não segue ligação nem
`..`, e os tetos de profundidade, entradas e bytes valem durante a varredura. Instalação fora dessa pasta vai para
`plugins_nao_lidos`, sem o caminho. Hooks de `hooks/hooks.json` e do campo `hooks` do manifesto entram com a origem
`plugin:<id>|<escopo>`: evento, matcher (a cópia de exibição, de até 200 caracteres e com caractere de controle e
surrogate trocados por espaço, e o SHA-256 do inteiro cru, que é o avaliado e o comparado [Decisão; revisão de
segurança da 1.7.7, R177-VAL-03; o cru, na segunda passada, R177B-A-01]), tipo, executável e SHA-256 dos scripts da
pasta do plugin. Servidores MCP de `.mcp.json` e `mcpServers` seguem as regras acima. Das skills, só a quantidade e os
caracteres de `description`: base de uma estimativa do contexto fixo (caracteres ÷ 4; não é medida — o `/context` do
Claude Code mede). Alertas de todos os hooks (`scripts/alertas_hooks.py`, regra no §2): `matcher_nunca_casa`,
`matcher_casa_tudo`, `matcher_indeterminado` (expressão que não pôde ser avaliada: o `re` do Python não a compila,
passou de 5 s num subprocesso — retrocesso exponencial — ou tem mais de 4096 caracteres; confira à mão [Decisão;
revisão de segurança da 1.7.7, R177-VAL-04]; também o matcher com caractere de controle ou surrogate, que a cópia
mostra como espaço, quando a avaliação não diz `matcher_casa_tudo` [Decisão; segunda passada, R177B-A-01]) e
`evento_fora_do_guarda` — hook do perfil ou de plugin em evento que não é o PreToolUse dos guardas; roda fora do
sandbox, com o que o host lhe entregar. Conteúdo de plugin não derruba nem trava o inventário: URL malformada dá host
nulo, surrogate solto vira espaço no que é exibido e caminho com NUL vai para `plugins_nao_lidos`, sem o texto
[R177B-A-02]; JSON com mais de 100 níveis de lista e objeto (ou que estoura o limite de recursão do leitor) vai para
`plugins_nao_lidos` com o motivo e, no perfil e na raiz (também o TOML do Codex), vale como o ilegível [R177C-B-02].
A forma de cada arquivo (do plugin, do perfil e da raiz) é conferida num lugar só, `FORMAS` em
`scripts/inventario_plugins.py`: fora dela — lista no topo, `"hooks": [..]`, matcher, comando ou `args` que não são
texto, `permissions` que não é objeto — o arquivo vale como ilegível, com o motivo, em `plugins_nao_lidos` ou em
`arquivos_nao_lidos` (perfil e raiz), sem reproduzir chave livre (a de um projeto é um caminho), e o inventário relido
de forma inesperada faz o `verificar` sair com 1 e o motivo [R177C-B-02, tipo inesperado]. Só a parte fora da forma
fica de fora (o grupo, o hook, o servidor, o evento ou a chave da raiz); o resto é lido, com os alertas, e o registro
de "não lido" guarda o SHA-256 do arquivo, que entra na comparação do `verificar`: qualquer mudança nele aparece
[R177D-3].
O `verificar` acusa hook acrescentado. Sobre um inventário do esquema 1, ele
mostra uma vez o que o esquema 2 passou a ver: confira e regrave. Ficam de fora: plugins em pastas de skills,
`--plugin-dir`, configurações gerenciadas, hooks no frontmatter de skills e agentes e pacotes `.mcpb`. Na sessão de
projeto da 1.7.10, os plugins entram justamente por `--plugin-dir`, a partir da área do titular no Ubuntu: quem os fixa
é o `hashes.json` dessa área, que o lançador reconfere a cada abertura (§5).

## 2. Hooks (R33, R52)
**Donos diferentes** [Livro p56]: Git (`pre-commit`), Claude Code (eventos do produto),
Codex (eventos do produto), orquestrador (transições do seu código). `hooks.json` sem
programa que o leia não automatiza nada.

Fatos conferidos [Verificado 2026-10-18]:
- Claude Code: configuração em `~/.claude/settings.json`, `.claude/settings.json`,
  `.claude/settings.local.json` (e `hooks/hooks.json` de plugins). **PreToolUse** bloqueia
  com `hookSpecificOutput.permissionDecision` (`allow`/`deny`/`ask`/`defer`) +
  `permissionDecisionReason` (campos `decision`/`reason` no topo estão depreciados para
  esse evento); código de saída 2 também bloqueia. **PostToolUse** roda depois da
  ferramenta e não desfaz o efeito.
- *Matcher* [Verificado 2026-10-21]: `*`, vazio ou ausente casam tudo. Só letras, dígitos, `_`, `-`,
  espaço, `,` e `|` formam lista exata (`Edit|Write` ou `Edit, Write`, com espaços em volta; `Edit || Write`
  (só letras, espaços e `|`) é lista exata e casa só os dois). Outro caractere faz expressão regular de
  JavaScript sem âncora: `Edit.*` também casa `NotebookEdit`, e a alternativa vazia de
  `tool == "Edit" || tool == "Write"` casa qualquer nome. MCP: `mcp__<servidor>__.*` (`mcp__memory` sozinho
  não casa nada; servidor de plugin: `mcp__plugin_<plugin>_<servidor>__<ferramenta>`). Em evento sem matcher
  (UserPromptSubmit, Stop e outros) o campo é ignorado. `MultiEdit` é legado. O inventário do host confere os
  matchers inteiros (§1).
- Com `mcp__.*` no matcher, o hook `assets/hooks/guarda_caminho.py` nega **toda** ferramenta MCP
  fora de `FUNDACAO_MCP_PERMITIDAS` — inclusive as de infraestrutura do próprio host (no
  aplicativo Claude Desktop, a família `mcp__ccd_*`: plano, sessões, painéis). A lista aceita
  padrões com `*`: libere `mcp__ccd_*` (ou o equivalente do host) junto com as ferramentas de
  leitura do projeto, senão a sessão em que o hook for instalado perde essas ferramentas
  [Decisão; auditoria final da 1.4.2, AF-08].
- `if` existe (uma regra no formato de permissão, "melhor esforço", só eventos de
  ferramenta). **Regras de arquivo só consultam `Edit(caminho)` e `Read(caminho)`;
  `Write(caminho)` é aceito e nunca consultado** → o `if: "Write(data/lab-hooks/**)"`
  do livro [Livro p57] não filtra; use `Edit(...)` ou valide o caminho no script.
- `args` existe em hooks do tipo `command` (forma exec, sem shell); no Windows o comando
  precisa ser executável real. `timeout` em segundos (padrão 600). `${CLAUDE_PROJECT_DIR}`
  disponível. `/hooks` só lê; `"disableAllHooks": true` desliga todos (não há interruptor por hook).
- Permissões: `deny` → `ask` → `allow` (primeira correspondência vence); exemplos
  `Read(./.env)`, `Read(./secrets/**)`; `Bash(curl *)` não é fronteira de segurança
  (não casa `/usr/bin/curl`).
- Sandbox: no **Windows nativo, comandos rodam sem sandbox**; use WSL2 (WSL1 não);
  `sandbox.failIfUnavailable: true` faz falhar se indisponível; só comandos de shell
  são isolados — ferramentas de arquivo, servidores MCP e hooks rodam fora.
- Codex: hooks em `hooks.json` ou `[hooks]` no `config.toml` (`~/.codex/` ou
  `.codex/` de projeto confiável); eventos incluem PreToolUse/PostToolUse; negação
  por `permissionDecision: "deny"`; confiança por hash (hook editado precisa ser
  confiado de novo); a documentação os chama de proteção, não fronteira completa.

Procedimento:
1. **Preventivo antes do observador** [3.0 R4.1–R4.3]: objetivo verificável no host em uso —
   segredos ilegíveis, escrita só em `projects/<projeto autenticado>/` e execução isolada, cada
   um com prova negativa e falha fechada se o mecanismo faltar. Claude Code: `permissions.deny`
   para segredos (1ª camada), PreToolUse com `assets/hooks/guarda_caminho.py` (2ª) e, no
   Windows, sandbox em WSL2 com `sandbox.failIfUnavailable: true`; Codex ou outro host:
   mecanismo equivalente conferido na versão instalada. Presença do mecanismo não prova o
   objetivo [auditoria da 1.4.1, A19].
2. Auditoria posterior (A11B): PostToolUse em `Write|Edit` que grava **só metadados**
   (sessão, evento, caminho relativo, resultado), com chave única
   (hook + sessão + `tool_use_id`) para não duplicar; sem chamadas de rede/IA [Livro p57].
3. Teste o script com payload fictício **antes** de ativar; depois prove o disparo real
   pelo produto (manual ≠ nativo) [Livro p57, p59].
4. Provas: escrita autorizada dispara uma vez; leitura e escrita fora do escopo não geram
   efeito (distinga "não despachado" de "rejeitado pelo script"); reentrega do mesmo
   evento não duplica; timeout registrado; desativado não executa [Livro p58].

Exemplo de bloco (mesclar, preservando entradas existentes; conferir na versão instalada;
alterar `.claude/settings*.json` do usuário exige decisão dele):
```json
{"permissions": {"deny": ["Read(./.env)", "Read(./secrets/**)", "Read(./state/**)"]},
 "hooks": {"PreToolUse": [{"matcher": "Edit|Write|MultiEdit|NotebookEdit|mcp__.*",
   "hooks": [{"type": "command", "command": "python",
              "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/guarda_caminho.py"], "timeout": 5}]},
  {"matcher": "Bash|PowerShell",
   "hooks": [{"type": "command", "command": "python",
              "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/guarda_identidade.py"], "timeout": 5}]}]}}
```
Sem `mcp__.*` no matcher, ferramentas MCP nem chegam ao hook. O `guarda_caminho.py` nega
toda ferramenta MCP que não esteja em `FUNDACAO_MCP_PERMITIDAS` (ele não sabe se a
ferramenta lê ou grava: libere as de leitura que o projeto usa) e falha fechado em evento
ilegível. Nega também `projects/` ou a pasta do projeto trocadas por ligação/junção e ligação
no caminho do destino; é consultivo — troca de ligação depois da checagem passa (ver
`../seguranca-isolamento.md` §5). O `guarda_identidade.py` (regime de dados reais) nega
comandos de shell que atribuam ou troquem `FUNDACAO_PRINCIPAL` de forma explícita —
guarda-corpo, não barreira: nome montado em tempo de execução, a API do kit chamada direto ou
a escrita direta em `state/` passam por ele (ver `../seguranca-isolamento.md`); o laboratório
pode liberar com `FUNDACAO_PERMITIR_TROCA_IDENTIDADE=1` no ambiente do lançador.
Na fundação, quem instala os hooks e os perfis no host é o titular, com
`assets/host/windows/preparar-maquina.ps1` (e `assets/host/wsl/preparar-wsl.sh` para a sessão de dados reais
no WSL2); ver `../seguranca-isolamento.md` §5 e `../fluxo-a-implantar.md` §Host.

**Hooks da 1.7.10** [Decisão; 1.7.10]. O preparo do host registra cada hook com `python3 -I -B` (no Windows,
`python -I -B`) e o caminho absoluto em `<raiz>/.claude/hooks/<hook>.py`; os de PreToolUse têm prazo de 10 s e
`onFailure: block` e negam em evento ilegível (falha fechada); o `aviso_copia.py` nunca bloqueia:

| Hook | Evento e matcher | Perfil | O que decide |
|---|---|---|---|
| `guarda_caminho.py` | PreToolUse `Edit\|Write\|MultiEdit\|NotebookEdit\|mcp__.*` | Ubuntu e Windows | escrita só no projeto; MCP só da lista |
| `guarda_identidade.py` | PreToolUse `Bash\|PowerShell` | Ubuntu e Windows | troca de identidade; comando que cite outro projeto; comando recursivo conhecido (`rg`, `grep -r`, `find`, `ls -R`, `tree`, `du`, `cp -r`, `tar`, `zip`, `rsync`, `Get-ChildItem -Recurse` e afins) sobre `projects/`, a raiz ou acima; comando acima de 16 KiB |
| `guarda_ferramentas.py` | PreToolUse `*` | só Ubuntu | só as ferramentas de `FUNDACAO_FERRAMENTAS`, a lista do `--tools`; desde a 1.7.11, também os agentes de arquivo, as skills e as ferramentas MCP que a ficha abriu, e as três travas do evento de subagente (abaixo) |
| `guarda_rede.py` | PreToolUse `WebFetch\|WebSearch` | Ubuntu e Windows | WebFetch só para domínio da ficha; WebSearch só com a ficha |
| `guarda_leitura.py` | PreToolUse `Read\|Grep\|Glob`, em grupo separado do de `mcp__.*` | Ubuntu e Windows | leitura de outro projeto e de `state/`; no Ubuntu, `/mnt/wslg/` e o filtro do Grep com barra invertida |
| `sinais_sessao.py` | SessionStart `compact` e a linha de status | Ubuntu e Windows | lembra a retomada depois da compactação |
| `regras_codigo.py` | SessionStart `startup\|resume\|clear\|compact` e SubagentStart (prazo de 3 s, sem bloquear) | só Ubuntu: o lançador o liga com o campo `regras_codigo` do projeto; no Windows nada liga o campo, então ele só é copiado para a raiz e não é registrado no perfil | entrega um texto fixo, o §1 de `references/codigo-enxuto.md`; sem o campo, não escreve nada. **Desligado por padrão**: a rodada P8 de 09/11/2026 mediu diff menor e nenhum ganho de tokens em tarefa pequena (`codigo-enxuto.md` §6) |
| `aviso_copia.py` | SessionStart `startup\|resume` (prazo de 5 s, sem bloquear) | só Windows | lembra a cópia semanal |

Os hooks decidem só pelo `tool_name` exato: matcher mais largo não amplia nada. Eles leem do `env` do perfil
`FUNDACAO_FERRAMENTAS`, `FUNDACAO_MCP_PERMITIDAS` (vazia no Ubuntu; no Windows, `mcp__ccd_*`), `FUNDACAO_DOMINIOS_WEB`,
`FUNDACAO_WEBSEARCH`, `FUNDACAO_PROJECT`, `FUNDACAO_RAIZ` e, no Windows, `FUNDACAO_SEM_DADOS`. Sem `FUNDACAO_RAIZ`
(perfil da 1.7.9 ou feito à mão), o `guarda_leitura.py` e o `guarda_identidade.py` deduzem a raiz pela pasta onde
estão instalados (`<raiz>/.claude/hooks/`), inclusive quando a raiz fica dentro de uma pasta chamada `projects`; o
perfil gerado pelo preparo põe `FUNDACAO_RAIZ`. Os hooks mudaram de conteúdo na 1.7.10: depois de atualizar a skill,
rode o preparo da máquina, que os recopia para `<raiz>/.claude/hooks`, e depois o do Ubuntu, que confere os da raiz
contra os da skill e refaz os hashes da área. O que cada um nega, os falsos positivos declarados e os limites:
`../seguranca-isolamento.md` §8.2. São guarda-corpos, não barreira do sistema.

**Hooks da 1.7.11** [Decisão; 1.7.11; lotes A1, L2 e P3]. O `guarda_ferramentas.py` ganhou quatro coisas, todas por
variável do `env` do perfil que o preparo gera da ficha assinada, sem ler arquivo: (1) `FUNDACAO_AGENTES`
(`<plugin>:<agente>=Ferramenta|Ferramenta,...`) abre na ferramenta Agent o tipo de cada agente de arquivo da ficha;
(2) três travas para o evento que traz `agent_id` ou `agent_type` (na sessão principal não valem): o `agent_type` tem
de ser um embutido ou um agente da ficha, e qualquer outro valor nega toda ferramenta (o subagente nasceu por um
caminho que a ficha não abriu); o agente de arquivo só usa as ferramentas dele; e o `cwd` do evento, só como texto, tem
de ficar em `projects/<p>` ou no temp do projeto; (3) `FUNDACAO_SKILLS` (`<plugin>:<skill>`): com ela no ambiente, a
ferramenta Skill só passa com o nome exato, o que fecha a skill embutida e a de plugin embutido (o perfil sem ficha
válida a leva com `-`, e a ficha sem skill também: nenhuma skill abre); (4)
`FUNDACAO_MCP_FERRAMENTAS`: a ferramenta MCP só passa com o nome completo `mcp__<servidor>__<ferramenta>` na lista da
ficha (§3). Lista malformada falha fechada só no que é novo. O `regras_codigo.py` entra só no Ubuntu e só com o campo
`regras_codigo` do projeto. O que o 2.1.302 manda como `agent_type` em cada caminho de subagente, a forma da entrada
da Skill no hook, se o hook `agent.spawn` de um plugin escapa ao guarda e quem preenche `projectAgentsElsewhere`
**não foram medidos** (M-A1 a M-A6 e M-S6 do canário, `../seguranca-isolamento.md` §8.7): a trava nega o que não reconhece.

## 3. MCP (R34)
Cliente (inicia e pede) · servidor (oferece *tools*, *resources*, *prompts*) · host [Livro p60].
Fatos conferidos [Verificado 2026-10-18]: protocolo vigente **2026-07-28** — sem sessões
nem `Mcp-Session-Id`; sem handshake `initialize`/`notifications/initialized` (versão e
capacidades vão em `_meta` de cada requisição); servidores **devem** implementar
`server/discover` (clientes podem chamá-lo); `ping` e `logging/setLevel` removidos;
Roots, Sampling, Logging, HTTP+SSE e DCR depreciados (janela ≥ 12 meses); pedidos de
entrada passam por *multi-round-trip* (`InputRequiredResult`). SDK Python `mcp` 2.x
estável (2.3.0 em 02/10/2026): `FastMCP` virou `MCPServer`; cliente `from mcp import Client`
com `mode='auto'` (sonda `server/discover` e cai para `initialize`), `mode='legacy'`
(força handshake) ou versão fixa; 1.x só recebe correções.
Registro nos hosts: Claude Code `claude mcp add --scope project` → `.mcp.json`
(escopos local/projeto/usuário); Codex `[mcp_servers.<nome>]` no `config.toml` ou
`codex mcp add`.

Procedimento [Livro p62–63; 3.0 R4.7–R4.13]:
1. Servidor oficial v2 com ferramenta delimitada (ex.: `manifesto_fontes(document_ids)`),
   ligada ao **mesmo** serviço e autorização do componente; stdout reservado ao protocolo,
   diagnóstico em stderr; anotações `readOnlyHint`/`idempotentHint`, `outputSchema`.
2. Identidade e projeto vêm do **lançador confiável** (ambiente do processo), nunca de
   argumento do modelo; `project_id` é filtro, não autorização.
3. Provas: conexão real, versão negociada registrada (não confundir com versão do SDK),
   descoberta, chamada permitida, documento de outro projeto negado (ausente também de
   dados estruturados e logs), ferramenta desconhecida, argumento inválido, servidor
   indisponível, componente desligado → negado via MCP, integração desligada → servidor
   não inicia; `is_error` conferido além de exceções de transporte.
4. Ameaças: *tool poisoning*, *rug pull* (hash das definições), sombreamento de nomes,
   injeção via resultado; meça tokens das definições de ferramentas.
5. HTTP local: bind 127.0.0.1 e validação de `Origin`; remoto exige OAuth 2.1 (fora do
   laboratório). Endpoint FastAPI isolado ≠ servidor MCP [Livro p63].
No kit: `fundacao/mcp_servidor.py` (ferramentas de leitura `listar_projetos`,
`listar_documentos`, `buscar`, todas pela autorização da fundação; identidade do processo;
as duas últimas também na CLI, `python -m fundacao conhecimento listar|buscar`)
e o ensaio `python <skill>/scripts/mcp_ensaio.py --raiz <raiz> --projeto <autorizado> --outro <nao-autorizado>`,
que sobe o servidor em processo separado (stdio), descobre as ferramentas, faz a chamada
autorizada, confere a negativa entre projetos (registrada na trilha) e encerra, sem rede.
Ensaiado nesta skill com o SDK `mcp` 2.3.0 já presente no ambiente (real-local; cenário
CEN-15 e teste `test_mcp.py`). Pasta `mcp/` sem `__init__` no caminho de importação (a raiz
da fundação, no uso normal) não é o SDK: sem ele instalado, o Python a montaria como pacote de
namespace, e o servidor a trata como "pacote mcp ausente", sem importar nada dela; o
`atualizar_fundacao.py checar` a recusa [revisão de segurança da 1.7.7, terceira passada,
R177C-B-03]. Verifique a presença do pacote no inventário
(`modulos_opcionais.mcp`) — é fato do ambiente, não da skill; ausente, instalar exige
autorização e cadeia fixada [Decisão; revisão de segurança da 1.4.5, #20]: (1) num ambiente
confiável com o mesmo SO, arquitetura e Python da venv de destino, o operador resolve
`mcp==2.3.0` (versão ensaiada; outra exige repetir CEN-15 e `test_mcp.py`) e gera
`requirements-mcp.txt` com todas as dependências transitivas em `==` e `--hash=sha256:`
(`pip download` + `pip hash`, ou `uv pip compile --generate-hashes`; confira as opções na
versão instalada); (2) revisa a lista e guarda o arquivo e seu SHA-256 fora das pastas de
projeto; (3) instala numa venv própria:
`<python-da-venv> -m pip install --require-hashes --only-binary :all: -r requirements-mcp.txt`.
Hash divergente ou dependência sem hash: o pip recusa — refaça (1)–(2), nunca afrouxe. Hash
prova que os bytes são os revisados, não que são seguros.
Pendente: registrar o servidor no host (Claude Code `claude mcp add`; Codex
`[mcp_servers.<nome>]`) altera a configuração do usuário e exige decisão dele; depois,
prove o disparo pelo host com a mesma negativa entre projetos.

**MCP na sessão de projeto** [Decisão; 1.7.10 e 1.7.11]. Servidor MCP **local** roda fora do sandbox, com o acesso total
do usuário (documentação de 31/10/2026: `../fontes-verificadas.md`), e continua fechado: a seção `mcp` da ficha recusa
comando, argumentos, variáveis e cabeçalhos. Sem a seção, vale o desenho da 1.7.10: a sessão carrega só o `mcp.json` da
área do titular, sempre `{"mcpServers": {}}`, com `--strict-mcp-config`; `FUNDACAO_MCP_PERMITIDAS` e
`FUNDACAO_MCP_FERRAMENTAS` ficam vazias, o `guarda_ferramentas.py` nega toda ferramenta `mcp__` e o perfil desliga os
conectores do claude.ai (`disableClaudeAiConnectors`).

**MCP do escritório, com todas as ferramentas** [Decisão; DECISAO-010 item 2, revista pela DECISAO-011 de 08/11/2026]. A
seção `mcp` da ficha abre **um** servidor, o conector remoto da conta do titular (CRM, base de conhecimento, acervo de
peças e Banco Nacional de Precedentes), com a lista nominal de **todas** as ferramentas dele no campo `ferramentas`
(até 32; sem curinga), as de consulta e as que criam, atualizam, salvam, propõem, confirmam e cancelam operações no
servidor. A tela de assinatura mostra em separado as que gravam: o nome decide (o que não tem nome claro de consulta
conta como "grava"), e o nome não prova o que a ferramenta faz. Não há processo local, então ele não entra na jaula; a
barreira é a lista positiva de nomes completos (o hook, o `permissions.deny` e o `--disallowedTools` que o preparo
gera). Como o lançador não passa `--strict-mcp-config` nesse caso, todos os conectores da conta carregam, e só os da
lista passam. O nome antigo do campo (`consulta`) é recusado. Risco aceito: a sessão pode criar, mudar e apagar dados
do escritório, inclusive de outros clientes que o conector entregar; um texto malicioso pode tentar levá-la a gravar;
no modo sem perguntas a gravação não pede confirmação. **Não medido** (M3 a M5 do canário): os conectores da conta na
CLI fixada e o efeito do `--strict-mcp-config`, o MCP por URL com OAuth, e o hook que nega MCP com o modo sem perguntas
ligado. O servidor MCP do kit (`fundacao/mcp_servidor.py`) não inicia numa sessão de projeto travada: ali a sessão usa
`python -m fundacao ...`, que vai ao porteiro (`../seguranca-isolamento.md` §2).

## 4. Skills (R35)
Fatos conferidos [Verificado 2026-10-18]: padrão Agent Skills — `name` 1–64 caracteres
`a-z0-9-` igual à pasta; `description` até 1.024 (o quê **e** quando usar); opcionais
`license`, `compatibility` (≤ 500), `metadata` (mapa de textos), `allowed-tools`
(experimental); corpo < 5.000 tokens / < 500 linhas; `references/`, `scripts/`, `assets/`;
validador `skills-ref validate`. Claude Code: `~/.claude/skills/<nome>/SKILL.md`,
`.claude/skills/<nome>/`, skills de plugins; mudanças valem na sessão sem reiniciar
(nova pasta raiz de skills: `/reload-skills`; renomear: reiniciar); campos extras
(`disable-model-invocation`, `user-invocable`, `argument-hint`, `model`, `context`, `agent`);
`disable-model-invocation` controla só a invocação pelo modelo. Codex: `.agents/skills`
(do diretório atual até a raiz do repositório), `~/.agents/skills`, `/etc/codex/skills`;
`~/.codex/skills` só por compatibilidade; invocação explícita `/skills` ou `$nome`.

Procedimento [Livro p64–67; 3.0 R4.14–R4.15]: skill **comum** (ex.: conferir-evidencias)
com fonte canônica em `components/skills/`, sem dados de clientes; skill **específica**
(ex.: preparar-fatos-juridicos) só no projeto. Distribua cópias rastreáveis por hash;
correção feita só na cópia instalada cria divergência. Prove descoberta, invocação
explícita, execução em dois projetos, **não seleção** fora do escopo, entrada que tenta
ampliar permissões, atualização 0.1.0 → 0.2.0 comparada e desativação pelo mecanismo do
host. Casos de gatilho: ≥ 10 positivos e ≥ 10 negativos. Skill não implementa
autorização ("confirme o projeto" orienta; quem decide é o código).
**Retirada de skill de host em dois passos** [Decisão; ensaio do titular com a skill caveman,
19/10/2026]: (1) desabilitar no registro da fundação (`componente desabilitar`, que avisa
`W_SKILL_DE_HOST_AINDA_NO_DISCO` enquanto o `SKILL.md` existir); (2) retirar a pasta do alcance do
host — mover para uma pasta de guarda fora de `.claude/skills/` (ou `.agents/skills/`), conferindo
os hashes — e confirmar que o host não a carrega mais. Só o passo 1 deixa a skill ativa no host.
**Skills aninhadas por projeto, com negações que acumulam** [Decisão; 1.7.10]. O nome de skill aninhada que um projeto
traz (o `scripts/instrucoes_aninhadas.py listar` dá os nomes e as negações sugeridas, §6) vai para o
`registry/projetos-host.json` (`aninhadas_negadas`), que só o titular grava
(`assets/host/preparo_host.py registrar-projeto --negar-skill <nome>`; os perfis negam às sessões a escrita nele). O
preparo soma os nomes de todos os projetos e os nega por `Skill(<nome>)` no perfil do Windows e no de cada projeto do
Ubuntu: o que um projeto trouxe aninhado fica negado também nos outros. Pela documentação (31/10/2026), desde a
2.1.260 o nome sem qualificação também bloqueia a skill aninhada qualificada, e uma regra `allow` não abre exceção numa
negação. Na sessão do Ubuntu, com `--setting-sources local`, as skills, os agentes e os comandos de
`projects/<p>/.claude/` não deveriam carregar (o lançador só avisa se existirem; o canário mede a carga de uma
`.claude/` em subpasta do projeto, não a desta pasta: §5). O caminho para levar uma skill a um projeto é o plugin
candidato (§5).

**Agentes de arquivo pela ficha** [Decisão; 1.7.11; DECISAO-010 item 6; lotes A1 a A3]. Agente só vem de `agents/<nome>.md`
de um plugin da ficha, instalado pelo preparo em `/etc/fundacao-ia/projetos/<p>/plugins/<plugin>/` (dono root) e chamado
como `<plugin>:<nome>`; os `.claude/agents` do projeto, de `data/`, do usuário e das managed settings seguem fechados.
O item de `plugins[]` ganha `agentes` (`nome`, `sha256` do arquivo, `ferramentas` e `modelo`): até 10 por plugin e 20 na
ficha; de 1 a 10 ferramentas dentre `Read`, `Grep`, `Glob`, `Edit`, `Write`, `TodoWrite` e `Bash` (`WebFetch` só com a
seção `webfetch`, `WebSearch` só com a busca aberta; nunca `Agent`, `Skill`, `NotebookEdit` nem MCP); o cabeçalho do
arquivo tem de dizer o mesmo, com `tools` obrigatório (sem ele o subagente herdaria todas as ferramentas da sessão).
O plugin com `agentes` ou `skills_com_scripts` tem de se chamar `<projeto>-<nome>` (erro, não aviso). O preparo grava
`FUNDACAO_AGENTES` e `FUNDACAO_SKILLS` no perfil, e o guarda aplica as travas do §2. A conferência lê a forma, não o
texto das instruções do agente (é o que o titular lê no `REVISAO.md`); um agente com `Bash` tem a autoridade da sessão
(prefira agentes de redação sem `Bash`).

**Skills com scripts, presas por hash** [Decisão; 1.7.11; DECISAO-010 item 6; lotes S1 a S3]. A ficha lista em
`skills_com_scripts` a skill, o SHA-256 do `SKILL.md` e, por script, o nome, o caminho exato
`skills/<skill>/scripts/<arquivo>.py`, o SHA-256 e o modo (`sessao`; o `caixa` fica para a 1.7.12). Só vale `.py`, sem
`#!` e sem bit de execução; todo `.py` do plugin tem de estar listado, e um a mais, a menos ou fora do lugar recusa o
plugin inteiro (shell, Node, binário e `.pyc` seguem recusados). Dependências: `requirements.lock` dentro da skill, com
`nome==versão` e `--hash=sha256:` em cada linha (sem opção, URL ou caminho; até 300 pacotes), a pasta das rodas que o
titular baixou com um Python limpo (a sessão não baixa) e o número de pacotes, que a tela da assinatura mostra. Na
sessão: `plugin_candidato.py montar --com-scripts`, `travar --skill <s> --rodas <pasta>` (grava o lock a partir das
rodas), `conferir --com-scripts` e `revisar --com-scripts` (a seção "Código que roda" do `REVISAO.md`, que marca o que
cada script importa e cita). No preparo do titular (sudo): as rodas vão para a área root pela cópia conferida, a venv é
montada de dono root, sem rede (`pip install --no-index --only-binary=:all: --require-hashes`), e o interpretador e a
árvore da venv entram no `hashes.json`. O script roda só pelo executor `fundacao-skill-<p> <plugin>:<skill> <script>
[-- args]`, que reconfere o script, a venv, o interpretador e a pasta atual a cada execução (falha fechada, código 2) e
grava `projects/<p>/outputs/skills/registro.jsonl`. **Limites que ficam**: no modo `sessao` o script tem a autoridade
dos comandos da sessão, e o executor prova a integridade do que roda, não o que ele faz; a sessão ainda pode rodar
qualquer código por fora dele; a venv é confiada no primeiro uso (o pip não gera saída idêntica byte a byte); o hash das
rodas prova que são as baixadas, não que são seguras, e um `.pth` delas roda a cada partida do interpretador; a trava de
projeto do executor é lógica com a raiz em `/mnt/e`. Skill da ficha tem de ter nome novo: o registro de negações só
cresce, e a negação do nome simples não tem exceção (o preparo recusa com o comando para renomear). Perfis feitos antes
da 1.7.11 falham a conferência até o preparo do titular refazê-los. **Não medido**: M-S1 a M-S7 e M-A1 a M-A6 do canário
(`../seguranca-isolamento.md` §8.7).

## 5. Plugins (R36)
Fatos conferidos [Verificado 2026-10-18]: Claude Code — `.claude-plugin/plugin.json`
(só `name` obrigatório); `claude plugin validate` é a checagem autoritativa (`--strict`
falha em avisos); catálogo `.claude-plugin/marketplace.json` exige `name`, `owner`,
`plugins` (cada um com `name` e `source`); `/plugin install <plugin>@<catálogo>`;
`claude plugin install|enable|disable|uninstall --scope user|project|local`;
`${CLAUDE_PLUGIN_ROOT}` muda a cada atualização. Formatos OpenAI (portátil e
`.codex-plugin/plugin.json`) não são equivalentes aos do Claude [Livro p68].

Procedimento [Livro p68–71; 3.0 R4.17]: catálogo local + plugin 0.1.0 só com a skill
comum → validar → instalar no escopo local (carregar por `--plugin-dir` não prova
instalação persistente) → executar com nome qualificado → 0.2.0 com o servidor MCP →
recarregar e conferir versão carregada → negativa entre projetos pela nova rota →
desativar (sem seleção, sem novas chamadas nem processos) → desinstalar só o plugin
(dados e evidências permanecem) → reinstalar versão preservada. Catálogo privado em Git
fixado por tag/commit, revisão de diff. Quadro: `assets/templates/COMPATIBILIDADE-HOSTS.md`.

### Plugin candidato do projeto (1.7.10)
[Decisão; 1.7.10.] Na sessão de um projeto, skill, agente ou comando só carrega como plugin candidato: montado,
conferido e revisado na sessão, aceito pelo titular, listado na ficha de aberturas assinada
(`../seguranca-isolamento.md` §8.3) e instalado pelo preparo do titular, depois do canário. Até lá, nenhuma sessão o
carrega (a confirmar: o `conclusao.carga_aninhada` do canário, item 12 de `assets/templates/CHECKLIST-PROJETO.md`,
mede com `--setting-sources local` a carga de skill e agente de uma `.claude/` em subpasta do projeto; para a
`projects/<p>/.claude/`, o ensaio não tem item, e o lançador só avisa). As recusas abaixo são do código (lista
positiva e cópia que não segue ligação), não barreira do sistema: com a raiz em `/mnt/e`, o sandbox não confinou os
comandos (`../seguranca-isolamento.md` §8.1). Quem decide é o caminho confiável: a regra do validador do kit (o módulo
`aberturas_plugins`, com o `aberturas_markdown`), que vale na `abertura preparar|verificar`, na ferramenta do titular
(`assets/host/fundacao_titular.py assinar-ficha`) e no instalador do preparo do Ubuntu. A ferramenta e o instalador
rodam fora da sessão, cada um com o kit da própria cópia da skill, e o instalador copia cada arquivo pelo manifesto
assinado. A conferência da sessão (`scripts/plugin_candidato.py`) aplica a mesma regra e recusa um pouco mais, como
guarda-corpo: um candidato montado à mão passa por esse a mais no caminho confiável.

1. **Montar** (sessão):
   `python <skill>/scripts/plugin_candidato.py montar --raiz <raiz> --projeto <p> --nome <n> --origem <pasta>`, com a
   origem dentro de `projects/<p>/`, copia para `projects/<p>/plugins-candidatos/<p>-<n>/`, que não pode existir. A
   origem é uma skill avulsa (com `SKILL.md`) ou uma árvore com `skills/`, `agents/` e `commands/` (uma
   `.claude/` ou um plugin); da raiz dela vem só a licença. Hooks, MCP, configuração e scripts ficam de fora,
   listados em `nao_copiados`, com aviso de "1.7.11" (o `.py` e o lock de skill só entram com `--com-scripts`, §4). Origem trazida pelo `scripts/importar.py` precisa ter sido
   importada com `--sem-neutralizar-extensoes`: sem essa opção, `.claude/skills`, `.claude/agents` e
   `.claude/commands` ficam no `EXTENSOES-NEUTRALIZADAS.zip`, e o `montar` não acha componente.
2. **Conferir**: `python <skill>/scripts/plugin_candidato.py conferir --pasta <candidato>` dá código 0 se conforme
   (imprime o manifesto e o `manifesto_sha256`) e 2 se recusado (com cada motivo; o que vem da regra do kit, que roda
   por último, termina com "(regra do kit, aberturas_plugins.conferir_pasta_do_plugin)"). Recusado: corrija na cópia
   de trabalho da origem, apague o candidato e monte de novo. Na sessão de um projeto, o script só lê pasta desse
   projeto.
3. **Revisar**: `python <skill>/scripts/plugin_candidato.py revisar --pasta <candidato> --saida <REVISAO.md>` grava o
   esqueleto da revisão do titular, arquivo novo, só em `projects/<p>/outputs/` (por exemplo,
   `outputs/plugins/<n>/REVISAO.md`; nunca em `.claude/` ou `.porteiro/`, nem como `CLAUDE.md` ou `AGENTS.md`). Todo
   texto do candidato vai entre crases, para nada esconder parte da revisão.
4. **Ficha e instalação**: a saída do `montar` e o `REVISAO.md` trazem a linha pronta da ficha,
   `{"nome": "<p>-<n>", "origem": "plugins-candidatos/<p>-<n>", "manifesto_sha256": "..."}`. O titular aceita, a ficha
   vai pela `abertura preparar`, e ele a assina pela ferramenta fixa dele. No Ubuntu, o preparo do titular (`sudo`)
   confere a origem de novo, copia arquivo a arquivo pela cópia conferida (`scripts/copia_segura.py`) para
   `/etc/fundacao-ia/projetos/<p>/plugins/<nome>/` e fixa os hashes; o lançador passa `--plugin-dir` com essa pasta.
   Só com o canário aprovado.
5. **Jeito novo de chamar**: o plugin se chama `<p>-<n>`; a skill vira `/<p>-<n>:<skill>` (por exemplo,
   `/criador-opensquad:opensquad` no lugar de `/opensquad`), e o agente, `<p>-<n>:<agente>`.

**O que o caminho confiável recusa** (lista positiva: o que não está nela recusa). O validador do kit recusa sozinho
cada item abaixo. A conferência da sessão recusa o mesmo no candidato, salvo o que depende da ficha (a origem e o
`manifesto_sha256` dela): pelas mesmas funções do kit (`allowed-tools` e menção `@`) ou pelas dela e, por último, pela
regra do kit. As recusas que a integração trouxe para o caminho confiável (`allowed-tools`, menção, segredo, nomes,
BOM e bit de execução) têm teste no kit (`assets/fundacao-kit/tests/test_aberturas_plugins_i16.py`).
- **origem e pasta:** pasta do plugin ausente, ligação ou que não é pasta; origem fora do projeto, em `data/` ou numa
  pasta protegida, ou com ligação no caminho; plugin sem `.claude-plugin/plugin.json`; `manifesto_sha256` diferente
  do da ficha ("o plugin mudou desde o manifesto da ficha");
- **nomes, recusados sem ler o arquivo:** nome fora do UTF-8 (o motivo mostra o nome escapado); nome forte e pasta de
  segredo da regra única, fora do hash e sem a exceção dos exemplos (`*.example`, `*.sample`), pelas listas de
  `assets/fundacao-kit/fundacao/core/manutencao.py`, iguais às de `scripts/regras_de_segredo.py` por teste,
  comparadas em NFKC, sem caixa e com a barra invertida como separador (a pasta de segredo vale em qualquer nível,
  também como nome de arquivo); e nome que muda entre o Windows e o Ubuntu: o que tem caractere da área privada do
  Unicode, que o DrvFs (`/mnt/<letra>` no WSL) troca por controle ou `" * : < > ? \ |` (e esses, de volta, pela área
  privada; sondado em 01/11/2026), o que tem um desses caracteres e o terminado em ponto ou espaço, que o Windows não
  abre pelo nome. Sem isso, o mesmo candidato teria outra recusa ou outro manifesto em cada sistema;
- **o que não é arquivo comum de um nome só:** ligação (link simbólico ou junção), vínculo físico, dispositivo e FIFO;
- **forma:** na raiz, só as pastas `.claude-plugin/`, `skills/`, `agents/` e `commands/` (a pasta `hooks/` recusa com
  a marca "1.7.11") e só os arquivos `README.md`, `LICENSE`, `LICENSE.md`, `LICENSE.txt` e `CHANGELOG.md`; em
  `.claude-plugin/`, só o `plugin.json`; em `skills/`, `agents/` e `commands/`, só Markdown (`.md`); `.mcp.json` e
  executável pela extensão, em qualquer ponto, com "1.7.11"; mods ficam de fora pela mesma lista;
- **`plugin.json`:** fora do JSON estrito (com chave repetida, por exemplo); `hooks`, `mcpServers` e `lspServers`
  ("1.7.11"); campo fora de `name`, `version`, `description`, `author`, `homepage`, `repository`, `license` e
  `keywords`; `name` diferente do nome do plugin na ficha;
- **tetos:** 500 arquivos, 1 MiB por arquivo, 16 MiB no total e 12 níveis de pasta;
- **texto de todo Markdown, também os da raiz:** fora do UTF-8; caractere de controle, controle de direção (U+202A a
  U+202E e U+2066 a U+2069) ou caractere de etiqueta do Unicode, CR sozinho, U+2028 e U+2029 (o YAML os lê como
  quebra de linha e veria chaves que a conferência não veria; LF e CRLF valem); e o shell embutido (`!` seguido de
  crase, ou cerca de crases ou de tils seguida de `!`), em qualquer ponto, com "1.7.11": o Claude Code 2.1.302 roda o
  bloco cercado sem âncora de começo de linha (`../fontes-verificadas.md`). A licença da raiz que não é Markdown
  (`LICENSE`, `LICENSE.txt`) só passa como texto UTF-8 sem controle, controle de direção, etiqueta, CR sozinho, U+2028
  nem U+2029;
- **BOM** (emenda E8): a marca U+FEFF só é tirada no começo de um Markdown, como o Claude Code 2.1.302 faz ao ler o
  cabeçalho, e o cabeçalho que vem depois dela é conferido: um BOM não esconde um cabeçalho com `hooks`. Em qualquer
  outro ponto, ela é caractere invisível e recusa;
- **cabeçalho de todo Markdown de `skills/`, `agents/` e `commands/`, também de um Markdown de apoio:** se a primeira
  linha com conteúdo começa com `---`, ela tem de ser só `---`, e o cabeçalho tem de fechar numa linha `---`, com, no
  máximo, espaço ou tab no fim. Recusa, com "1.7.11": o cabeçalho fora dessa forma; a chave de primeiro nível fora da
  lista do tipo da pasta (como `permissionMode`, `context`, `agent` e `version` numa skill), a linha que não é chave e
  o cabeçalho todo recuado; `hooks` ou `mcpServers` em qualquer ponto do cabeçalho (num valor, numa chave recuada ou
  num comentário); e o recurso de YAML que montaria uma chave sem a conferência ver: barra invertida, etiqueta (`!`),
  âncora (`&`), alias (`*`), mesclagem (`<<`) e chave complexa (`?`);
- **skill e comando** (todo `SKILL.md` de `skills/` e todo Markdown de `commands/`, também em subpasta: o que o
  Claude Code invoca):
  - o `allowed-tools`, em toda ocorrência da chave: fora do formato simples (curinga fora de parênteses, escape,
    âncora ou bloco); com `Bash`, `PowerShell`, `pwsh`, `Shell`, `KillShell`, `KillBash`, `Monitor`, `WebFetch` ou
    `WebSearch` (pelo começo do nome: `BashOutput` também) ou com um nome que tenha `mcp`, que só abrem pela ficha e
    pelo perfil gerado dela (MCP, só na 1.7.11); com o que estiver fora de `Read`, `Grep`, `Glob`, `Write`, `Edit`,
    `MultiEdit`, `NotebookEdit`, `TodoWrite`, `Task`, `Agent` e `Skill`; e com especificador entre parênteses que
    aponta para fora, pelas formas da menção (abaixo), também o `..` sozinho, como em `Read(..)`;
  - a menção com `@` para fora do plugin, em todo o texto: caminho absoluto, `~`, `%`, letra de unidade (também a
    relativa do Windows, `C:x`), `file:`, um componente `..` (a barra, a barra invertida e o `#` separam) ou `$` em
    qualquer ponto do alvo. O `$` conta porque o Claude Code 2.1.302 troca os argumentos (`$ARGUMENTS`, `$1`, `$nome`)
    e as variáveis (`${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PROJECT_DIR}`, `${CLAUDE_PLUGIN_DATA}`, `${CLAUDE_SKILL_DIR}`)
    antes de colher as menções, e o mesmo no `allowed-tools` (`../fontes-verificadas.md`). A menção é colhida como o
    2.1.302 a colhe, com as duas varreduras dele, cada uma à parte: a forma entre aspas duplas (`@"..."`, a menção com
    espaço no caminho), que cruza quebra de linha; e cada trecho sem espaço que começa com `@` (ou a traz logo depois
    de uma pontuação chinesa ou japonesa). O kit soma uma varredura larga (aspas duplas, aspas simples ou o trecho até
    o próximo espaço). Assim, uma menção dentro de um trecho entre aspas, mesmo cruzando linha, não fica escondida; um
    teste diferencial prende isso contra uma transcrição da leitura do 2.1.302;
- **bit de execução** (emenda E9): fora do Windows, o arquivo com bit de execução recusa, com "1.7.11". Numa montagem
  9p ou drvfs sem a opção `metadata` (o DrvFs do WSL, `/mnt/<letra>`), todo arquivo aparece 0777, e o bit não prova
  nada: ali ele não conta, e decide o conteúdo (o arquivo que começa com `#!`, ELF ou MZ recusa, com "1.7.11"). O kit
  acha a montagem no `/proc/mounts`, sem executar programa, pelo objeto aberto, não pelo caminho, que uma ligação posta
  depois da abertura desviaria. No ext4 e com `metadata`, vale o bit; no Windows, o kit não olha bit nem conteúdo. A
  conferência da sessão confere o conteúdo em todo sistema; o kit, só no DrvFs sem `metadata`, o que a emenda E4
  permite (a sessão pode ser mais estrita).

**O que só a conferência da sessão recusa** (guarda-corpo: o kit aceita, e um candidato montado à mão passa por isso
no caminho confiável; a forma inteira está no docstring de `scripts/plugin_candidato.py`):
- na raiz, `README.md` e `CHANGELOG.md`: lá, só a licença (`LICENSE`, `LICENSE.md` ou `LICENSE.txt`);
- no `plugin.json`, `homepage`, `repository`, `license` e `keywords` (só `name`, igual à pasta, `description`,
  obrigatória, `version` e `author`) e o arquivo acima de 64 KiB;
- comando ou agente fora do primeiro nível de `commands/` e `agents/`, arquivo solto em `skills/`, `SKILL.md`
  aninhado, skill sem `SKILL.md` e candidato sem skill, agente nem comando;
- no cabeçalho, as chaves `arguments` e `disallowed-tools` e a chave repetida; o agente sem `name` ou `description`;
  o nome da pasta da skill, o do comando e o `name` do cabeçalho fora da forma de nome de skill do preparo do host
  (sem `:` e sem `.` no fim);
- nome oculto (salvo `.claude-plugin`), `CLAUDE.md` e `AGENTS.md`, e pastas como `hooks/`, `bin/` e `node_modules/`
  abaixo da raiz;
- o resto do que não funciona num nome do Windows (nome reservado, como `CON` e `NUL`, caractere invisível ou de
  controle que o kit não confere no nome e mais de 255 bytes) e dois nomes que só diferem pela caixa ou pela forma
  Unicode;
- o arquivo que começa com `#!`, ELF ou MZ fora do DrvFs sem `metadata` (acima);
- mais de 10.000 arquivos e pastas na varredura.

Nome do plugin: o da ficha (minúsculas, números e hífen, até 64 caracteres), que a `abertura preparar` exige. Com
`--`, fora do kebab-case, ou citando `claude`, `anthropic` ou `cc-plugin`, ele sai com aviso: o Claude Code reserva
nomes assim (`../fontes-verificadas.md`), e a carga com `--plugin-dir` na versão fixada se confirma no canário.

**O que o titular revisa no `REVISAO.md`:** a identificação (pasta, conformidade e `manifesto_sha256`); os
componentes, com o que cada skill, agente e comando faz, as ferramentas e o modelo do cabeçalho e o jeito novo de
chamar; os trechos marcados — instruções que parecem mandar ignorar regras ou ler fora do projeto, caracteres
invisíveis, scripts e comandos citados, domínios citados (que só valem se forem para a ficha, em `rede.dominios` e
`webfetch.dominios`), nomes e trechos de segredo (com o valor longo mascarado) e ferramentas citadas —; a lista de
arquivos, com o começo do SHA-256; e a decisão, com a linha pronta da ficha. O esqueleto só marca, sem julgar: a
fundação confere a forma, e o texto das instruções é o titular quem revisa.

**Uma regra de conteúdo e uma receita de manifesto** [Decisão; 1.7.10; emendas E3 e E4]. O
`plugins[].manifesto_sha256` da ficha é um só: o `sha256_do_manifesto` do kit
(`assets/fundacao-kit/fundacao/core/aberturas_plugins.py`), o SHA-256 do JSON compacto (chaves ordenadas, separadores
`,` e `:`, UTF-8 sem escape) da lista `{caminho, bytes, sha256}` dos arquivos, em ordem de caminho. O mesmo valor sai
da `abertura preparar|verificar`, da ferramenta do titular, do `plugin_candidato.py` (`conferir`, `revisar` e a linha
pronta da ficha) e do instalador do preparo do Ubuntu, sem réplica. A regra de conteúdo do caminho confiável é a do
validador do kit; a conferência da sessão pode ser mais estrita, nunca mais frouxa. Ela aplica as regras dela e, por
último, a do kit (`conferir_pasta_do_plugin`): o que o kit recusa, ela recusa, e o manifesto que o kit calcula, lendo
os bytes de novo, tem de ser o dela. Comuns às duas, no mínimo: o shell embutido sem âncora, a recusa de CR sozinho,
U+2028 e U+2029, e o cabeçalho que quebra em toda quebra de linha e fecha só numa linha `---` (com espaço ou tab no
fim, no máximo). Os testes de `scripts/tests/test_plugin_regra_unica_1710.py` prendem as duas coisas: a receita, nas
três pontas sobre a mesma pasta (sessão, kit e instalador); e a implicação, sobre um conjunto de candidatos aceitos e
recusados: conforme na sessão implica sem erro no kit, o mesmo `manifesto_sha256` e a linha da ficha aceita.

**Limites que ficam** (registre sempre):
- no texto, as marcas de direção U+200E, U+200F e U+061C ficam fora das faixas do controle de direção (acima) e
  passam, no kit e na sessão. A revisão do titular (`REVISAO.md`) conta U+200E e U+200F entre os caracteres
  invisíveis; o U+061C, não;
- a regra lê o arquivo, não a invocação: o argumento preenchido ao chamar a skill ou o comando (`$ARGUMENTS` e afins)
  pode trazer uma menção `@` inteira, que o Claude Code colhe do texto já expandido. Nenhuma regra estática fecha
  isso. A barreira é a negação de leitura do perfil do projeto (`../seguranca-isolamento.md` §5), a confirmar no
  canário, que ainda não tem item para a menção;
- o conteúdo decide só por `#!`, ELF e MZ. Um formato que o `binfmt_misc` do WSL roda por outra mágica (os bytes do
  começo que o identificam), registrada à parte (Java, por exemplo), fica fora dessa lista; somar as mágicas ativas
  fica para a 1.7.11. Como todo arquivo do plugin tem de ser texto UTF-8, as mágicas binárias já recusam; sobra uma
  mágica de texto registrada por root;
- no DrvFs, um texto com o bit pode ser rodado por um shell, que lê como script o que o sistema não reconhece. Esse
  arquivo fica na área da sessão, onde o isolamento em `/mnt/e` é lógico. A cópia que o preparo do Ubuntu instala em
  `/etc/fundacao-ia/projetos/<p>/plugins/<nome>/` é de dono root e sem bit de execução. Montar o DrvFs com
  `metadata` (no `/etc/wsl.conf`) fica com o titular, na 1.7.11;
- o kit do Windows (a ferramenta do titular e a `abertura preparar` ali) não confere o conteúdo; a sessão o confere em
  todo sistema, e o instalador do Ubuntu, com a raiz num DrvFs sem `metadata`, também. Um candidato mudado depois da
  conferência da sessão pode passar na assinatura do Windows e cair no instalador: falha fechada.

### Plugin entregue pela skill: `codigo-enxuto`
[Decisão; ponytail, P2 e P3 — ideias e textos do ponytail (MIT), traduzidos e adaptados; `AVISOS-DE-TERCEIROS.md`.] A skill
traz um plugin pronto, só em Markdown, em `assets/plugins/codigo-enxuto/`: as skills `enxuto`, `enxuto-revisao`,
`enxuto-auditoria` e `enxuto-dividas`, o `plugin.json` e o `LICENSE` com os dois avisos de licença. No pacote, as skills
se chamam `SKILL.modelo.md`: o pacote tem um único `SKILL.md` (CEN-11, que também protege o envio do zip ao claude.ai), e
o Markdown entra na varredura de injeção. Ele não abre a forma: `python <skill>/scripts/plugin_codigo_enxuto.py montar
--raiz <raiz> --projeto <p>` copia as skills com o nome `SKILL.md` e o `LICENSE` para uma origem nova em
`projects/<p>/outputs/plugins/codigo-enxuto/origem/` (sem seguir ligação, só dentro do projeto, lista fixa de arquivos),
chama o `montar` do item 1 e apaga a origem; o `conferir` aceita o candidato `<p>-codigo-enxuto` como qualquer outro, que
segue o caminho de sempre: revisão, ficha assinada, canário e preparo. A parte do ponytail que roda código não entra como plugin: os hooks dele são
JavaScript, gravam estado no perfil do usuário e rodam fora do sandbox, e hook, `userConfig`, mods, `.js` e `.mcp.json`
de plugin continuam recusados (o código ainda traz a marca "1.7.11"). O que valia dos hooks, injetar um texto fixo,
é o `assets/hooks/regras_codigo.py` da fundação (§2), ligado pelo campo `regras_codigo` do `projeto.json`. A prova
negativa e o `montar` de uma árvore no formato do ponytail (`hooks/` e `scripts/` em `nao_copiados`) estão em
`scripts/tests/test_plugin_codigo_enxuto.py`, que prova também que o script de montagem recusa nome fora da lista e ligação. A regra, a revisão, as dívidas e a medição:
`references/codigo-enxuto.md`.

### Jaula do Criador: navegador e Codex (1.7.11)
[Decisão; DECISAO-010 itens 3 e 4; desenho da jaula; camadas, rede e limites: `../seguranca-isolamento.md` §8.7.] O
navegador e o Codex rodam programas na máquina e guardam logins, então só abrem pela jaula (bubblewrap que começa vazia,
outro usuário do Linux, proxy de lista), com a seção na ficha assinada, o canário da jaula aprovado e o preparo do
titular. **Navegador** (seção `navegador`: `dominios`, `logins` e `modos`): perfil novo e só do projeto; o titular entra
nos sites por uma janela dele (`abrir-navegador-<p> login <site>`); os modos são `sessao`, `login` e `captcha`; o
navegador é o Chromium do Playwright 1.64.1 (revisão 1248), instalado do arquivo de travas `jaula-navegador.lock`, com
as quatro rodas fixadas pelo SHA-256 do PyPI e a árvore do Chromium em confiança no primeiro uso (o Playwright não
publica o hash do navegador); o invólucro `chromium-sem-disfarce` impõe "sem disfarce" e desliga o ECH, que o proxy recusa.
**Codex** (seção `outras_llm`: o provedor `openai-codex` pela conta do ChatGPT, os modos `exec` e `titular`, o teto de
chamadas por dia e o R55 com plano e data da conferência, válida por 90 dias): binário `rust-v0.166.0` fixado em
`pins-codex.json` por tamanho e SHA-256 (a assinatura sigstore não é verificada na instalação), `CODEX_HOME` privado,
`config.toml` imposto com `--strict-config` e rede só para `chatgpt.com`, `auth.openai.com` e `api.openai.com` (fonte e
data: `../fontes-verificadas.md`). Com a conta do ChatGPT só a janela do titular (`titular`) abre: o Codex da sessão (`exec`)
fica fechado no preparo e na entrada fixa, porque um comando que ele rodasse a pedido da sessão leria o login do `CODEX_HOME`;
para a sessão usar o Codex, a decisão é do titular: a chave de API do projeto, com teto de gasto. **Não medido** (M6 e M7): o sandbox do Chromium, o Wayland, `/sys` e o limite de
memória virtual na jaula; o sandbox próprio do Codex dentro da jaula (a sonda `sandbox_codex` do canário da jaula mede;
se não abrir, `features.use_legacy_landlock` é a alternativa a medir), a rede dos comandos dele e os domínios que ele de
fato pede. Até lá valem as opções mais seguras (sandbox do Codex ligado, `workspace-write` sem rede).

## 6. Quando usar o quê [3.0 R4.16]
Instrução permanente → AGENTS.md/CLAUDE.md · procedimento repetível → skill · contexto
isolado → subagente · dados externos com autorização → MCP · garantia determinística →
hook/permissão · distribuição → plugin. Fixe versão e hash de todo componente externo
(R54) e revise o diff a cada atualização.

**Texto sempre carregado custa mais** [Decisão; 1.7.7; método adaptado de Harness², P5]: o corpo do `SKILL.md`, a
descrição dele e o `AGENTS.md` gerado entram em toda sessão e competem com o espaço do trabalho. Antes de pôr uma
regra ali, prefira, nesta ordem, uma referência carregada sob demanda, um script, um subagente e um hook. Os três
têm teto em caracteres que só desce (`scripts/tests/test_orcamento_texto.py`): regra nova paga com um corte ou vai
para a referência da etapa; subir o teto é mudança de critério, com motivo registrado.

**Instruções da raiz e pastas de dados** [Verificado 2026-10-21; Decisão; 1.7.0]: o Claude Code carrega ao iniciar
o `CLAUDE.md` da pasta da sessão e das pastas acima (os de subpastas, quando lê arquivos nelas); `@AGENTS.md` dentro
dele importa sem duplicar, e o `AGENTS.md` sozinho só é lido direto quando não há `CLAUDE.md` (2.1.277 ou
posterior); recomendação: menos de 200 linhas por arquivo. O Codex lê `AGENTS.md` da raiz do Git até a pasta atual
(sem Git, só a pasta atual), até 32 KiB. Na fundação, `python <skill>/scripts/instrucoes_raiz.py gerar --raiz <raiz>`
escreve o `AGENTS.md` (resumo gerado entre marcadores, sem nomes de projetos, e um trecho do titular que a skill
preserva) e o `CLAUDE.md` com `@AGENTS.md`; o C6 os regenera, e as chamadas aos provedores rodam numa pasta
temporária vazia, sem eles. Pasta `data/` é dado: o perfil do host exclui `**/projects/*/data/**` das instruções
(`claudeMdExcludes`, globs de caminho absoluto, em qualquer camada de configuração); skill em `.claude/skills/` de
uma subpasta é carregada quando a sessão lê ou edita ali, sem configuração que desligue isso — negue-a por nome
(`Skill(<nome>)`, opção `--negar-skill` de `assets/host/preparo_host.py perfil-windows|perfil-wsl`) a partir de
`python <skill>/scripts/instrucoes_aninhadas.py listar --raiz <pasta>` (só lê; lista instruções, skills, agentes,
comandos, regras, MCP e configurações aninhados, com as negações sugeridas; não segue ligação e tem tetos — código 1
quando o inventário fica parcial) [auditoria Codex Security da 1.7.6, #7].
