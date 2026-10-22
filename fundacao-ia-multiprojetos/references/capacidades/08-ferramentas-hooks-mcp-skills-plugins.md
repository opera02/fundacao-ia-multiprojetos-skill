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
`--plugin-dir`, configurações gerenciadas, hooks no frontmatter de skills e agentes e pacotes `.mcpb`.

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
`listar_documentos`, `buscar`, todas pela autorização da fundação; identidade do processo)
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
