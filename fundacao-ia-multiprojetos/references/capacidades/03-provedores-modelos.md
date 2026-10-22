# 03 — Múltiplos provedores e modelos: rotas, alternativas e continuidade

Requisitos: R12, R13, R14, R15 (R39 orçamento). Aulas: A03 [Livro p16–19], A08
[Livro p40–43]; 3.0 §3.1 (seletor de rota). Trilha: essencial.

## Objetivo operacional
Pelo menos **dois provedores autorizados** participam funcionalmente pela fundação,
com rota identificada, roteamento por tarefa, alternativa autorizada em falha e
continuidade por **estado persistido** (não pela memória da conversa).

## Acessos são regimes diferentes [Livro p16, p40]
Assinatura de aplicativo · CLI (programa de terminal) · API (programa↔serviço, com
autenticação e cobrança próprias) · SDK (biblioteca para usar uma interface). SDK não
transforma assinatura em crédito de API. Transferência manual entre janelas é
"transferência assistida", nunca integração programática [Livro p16–17, p40].

## Fatos conferidos [Verificado 2026-10-18] — reconfira a cada mudança de conta/canal
- **Anthropic / Claude Code:** OAuth das assinaturas destina-se ao uso comum do
  Claude Code; produtos e serviços (inclusive com Agent SDK) devem usar chave de API.
  Modo `--bare` nunca lê credenciais OAuth/keychain, ignora hooks, skills, plugins e
  MCP e exige `ANTHROPIC_API_KEY` — não é atalho pela assinatura. Sem `--bare`,
  `claude -p` executa hooks de `.claude/settings.json` e servidores de `.mcp.json`
  mesmo em pasta não confiável. Saída JSON traz `result`, identificador de sessão,
  `total_cost_usd` e `usage`; confira `is_error` além do código de saída.
- **Créditos de API do Max:** Max 5x US$ 100/mês, Max 20x US$ 200/mês (Team por
  assento, teto US$ 500); vinculação a organização no Console; não acumulam; Pro e
  Enterprise inelegíveis. **Páginas oficiais conflitam** sobre cobrir `claude -p` sem
  chave de API: trate créditos como rota `api_creditos` (chave da organização
  vinculada) e confirme na conta antes de usar.
- **OpenAI / Codex:** login ChatGPT (assinatura) ou chave de API (uso faturado); a
  chave de API é o padrão recomendado para uso programático/CI; `codex login status`
  informa o modo. `codex exec --json` emite JSONL (`thread.started`, `turn.started`,
  `turn.completed`, `turn.failed`, `item.*`, `error`); uso em
  `turn.completed.usage` (`input_tokens`, `cached_input_tokens`, `output_tokens`,
  `reasoning_output_tokens`). Sandbox padrão do exec: somente leitura; `--full-auto`
  foi descontinuado; `--skip-git-repo-check`, `-o/--output-last-message`,
  `--output-schema`, `--ephemeral` existem.
- Comandos mínimos do livro, como forma documental: `codex exec --json "Responda
  apenas: PRONTO"` e `claude -p "Responda apenas: PRONTO" --output-format json`
  — formatos diferentes, dois leitores [Livro p41].

## Seletor de rota [3.0 R1.1; Decisão]
Política `registry/route_policy.json`: `interativo` → `cli_assinatura` (somente o
titular) → `api_creditos` (teto) → `api_paga` (teto) → `local` → `simulado` (rotulado).
**Se outra pessoa usa a fundação, a rota de assinatura fica desligada.** Tipo de tarefa
sem rota declarada **falha fechado** (não herda a padrão); tarefas `sigiloso` só em
rota local ou comercial sem treino por padrão (ver `references/privacidade-sigilo.md`).
Desvio local da rota `sigiloso` (decisão do titular) só vale registrado e assinado [Decisão; 1.7.0; avaliação E11,
F-05, 1.7.4]: o SHA-256 de `registry/route_policy.json` em `registry/configuracao-decidida.json`
(`{"schema_version": "fundacao.configuracao_decidida/1", "itens": [{"arquivo": "registry/route_policy.json",
"sha256": "<hash>", "decisao": "projects/<projeto>/decisoes/<id>.json"}]}`), e a decisão citada é um **aceite** do
módulo de decisões, assinado pelo titular (§2 de `references/seguranca-isolamento.md`), cuja entrega é uma cópia exata
da política em `outputs/` do projeto (`decisao preparar --tipo aceite --entrega outputs/<cópia>`; o titular assina; a
IA roda `decisao registrar` e grava o item), e que continua a decisão **vigente** da sua tarefa na trilha (uma rejeição
ou correção registrada depois revoga o desvio). Documento qualquer (um `.md` da decisão) não aprova. Sem esse aceite,
ou com a política mudada depois dele, `load_policy` deixa o desvio **sem efeito** (vale a rota distribuída, só
`local`; o roteador mostra cada rota ignorada) e o `checar` da atualização (C6) avisa; a suíte da raiz confere a rota
que vale. A conferência usa o hash dos mesmos bytes que valem (revisão de segurança da 1.7.4).
Alternativa: só para destino **autorizado**; cada tentativa registrada; sem repetição
infinita; erro permanente não se repete na mesma rota [Livro p170–172].
Tetos por rota (`max_calls`, `max_usd`) valem **antes** da chamada e contam toda tentativa
cuja CLI chegou a iniciar, também a que falhou por falta de login: nada prova que ela não
chegou ao provedor [avaliação E11, F-04 — antes, "401" ou "login" no texto do erro tiravam a
chamada da conta]. Só não contam as que não saíram (executável ausente, entrada recusada antes
de iniciar: `dispatched=false`). Resíduo conhecido: um erro do sistema depois de a CLI iniciar (por
exemplo, ao encerrar a árvore de processos sem Job Object) ainda sai como não iniciada — raro, sem
alcance demonstrado [revisão de segurança da 1.7.4]. Custo de chamada anterior não medido bloqueia rota com
teto de custo (falha fechada) até a administração conferir o custo numa fonte externa e
reconciliá-lo: `python -m fundacao rota gasto --rota <r>` lista as tentativas sem custo;
`python -m fundacao rota custo --rota <r> --tentativa <event_id> --custo-usd <valor>
--fonte "<painel ou fatura>"` registra o valor (uma vez por tentativa, evento na trilha).
Custo só vale como Decimal finito ≥ 0: informado negativo, NaN ou infinito conta como não
medido, e `max_usd` inválido bloqueia a rota [varredura da 1.4.5, #17].
[Decisão; auditoria externa da 1.3.4] Com teto, a capacidade é **reservada** numa transação
curta antes do despacho (que serializa entre conexões e processos) e a reserva é finalizada,
por ID e de forma idempotente, junto com o registro da tentativa; nenhuma transação fica aberta
durante a chamada externa. Duas chamadas simultâneas com `max_calls=1`: só uma entra no
adaptador. Chamada interrompida (exceção ou queda do processo) continua contando, com custo não
medido, até a administração reconciliar — `rota gasto` lista `reservas_em_andamento`, e
`rota custo --tentativa <rsv_...>` fecha a reserva de um processo que caiu.
Resposta de rota simulada sai como `succeeded_simulated`, nunca como `succeeded`.

## Implementação
1. Contrato único de pedido/resultado: `project_id`, `task_id`, `provider_id`, rota,
   modelo informado pelo serviço (ou `unknown`), horário, duração, estado, texto/arquivo,
   identificador da chamada, consumo disponível [Livro p40].
2. Adaptadores por CLI com argumentos separados, timeout, captura controlada, leitores
   específicos (JSON × JSONL), sem flags de acesso irrestrito [Livro p41]. O agente do
   provedor **não herda a raiz da fundação**: cada chamada roda numa pasta temporária vazia,
   sem ferramentas nem MCP e sem as configurações do usuário [Decisão; flags conferidas em
   2026-10-18 — `references/fontes-verificadas.md`]. Claude: `--tools ""`,
   `--disallowedTools "mcp__*"`, `--strict-mcp-config`, `--restricted`, `--max-turns 1`,
   `--no-session-persistence`, `--permission-prompts none`, `--max-budget-usd <saldo do teto>`.
   Codex: `--sandbox read-only`, `--ephemeral`, `--ignore-user-config`, `--ignore-rules`
   (a documentação não diz se o modo somente leitura impede ler fora da pasta: trate como
   não isolado para leitura). Opções conferidas também no `--help` das versões instaladas
   (Claude Code 2.1.302: `--max-turns` não aparece no `--help`, mas está definida no
   executável; codex-cli 0.163.0). O **prompt vai pela entrada padrão**: `codex exec … -`
   e `claude -p "<instrução fixa>"` com tarefa e dados na entrada (no Windows, uma CLI
   instalada como `.cmd` passa a linha de comando pelo cmd.exe, que cortaria o prompt na
   primeira quebra de linha e interpretaria `&`, `|` e aspas; opção com esses caracteres
   numa CLI `.cmd`/`.bat` é recusada). O processo do provedor recebe **ambiente mínimo**
   (variáveis do sistema e a pasta de configuração da CLI; nunca `FUNDACAO_*` nem chaves de
   API — na rota de assinatura, uma chave no ambiente faria a CLI cobrar créditos de API;
   variáveis a mais só por `variaveis_extras`). A entrada vai em bytes UTF-8 (sem conversão
   de fim de linha) e o prazo, contado desde o início, encerra a CLI e **todos os
   descendentes** — no Windows por um Job Object (o `taskkill /T` fica só como recurso se o
   sistema recusar o Job Object): numa CLI `.cmd`, matar só o cmd.exe deixava o neto (node)
   segurando as saídas, e a chamada esperava por ele. Entrada e saídas correm em threads, então
   o prazo vale também quando a entrada passa do buffer do pipe e a CLI demora a lê-la. A CLI e
   todos os descendentes ficam num Job Object (Windows; nos demais, o grupo de processos — ramo
   não executado aqui, que não alcança descendente com sessão própria): quando a chamada
   termina, ou no prazo, o que sobrar é encerrado — inclusive um órfão que herdou as saídas,
   que antes prendia a resposta. A saída também tem teto, porque o prazo não limita memória: stdout
   acima de 32 MiB ou stderr acima de 4 MiB encerra a árvore na hora, e a chamada sai `invalid_output`,
   contada no teto da rota (a CLI começou) [auditoria Codex Security da 1.7.6, #9; executor em
   `assets/fundacao-kit/fundacao/core/processo.py`]. Falha ao iniciar o processo e prompt acima do limite
   saem como resultado `failed`, dentro do contrato. Isso reduz a superfície, mas
   não é barreira: antes de liberar a rota, prove com um documento-canário de outro projeto
   na raiz. O canário é necessário, não suficiente (uma negativa não prova que outra instrução
   não leia): com dados reais numa fundação multiprojeto, a rota Codex CLI fica **desligada**
   até o processo rodar sob conta do SO, contêiner ou VM que só enxergue as entradas da tarefa e
   a pasta temporária; prefira rota sem ferramentas de arquivo [Decisão; revisão de segurança
   da 1.4.5, #9]. No kit, `CodexCLIProvider` só roda com `isolamento_leitura` declarado — a
   descrição desse isolamento externo, que quem habilita prova com canário de outro projeto e
   de `state/` (o kit não a confere); sem ela, devolve `disabled` sem iniciar processo.
3. O núcleo autentica a identidade e autoriza o projeto **antes**; o adaptador recebe só
   o contexto necessário e não amplia o projeto [Livro p40].
4. Uso normalizado sem dupla contagem: Claude entrada total = `input_tokens` +
   `cache_creation_input_tokens` + `cache_read_input_tokens`; Codex `input_tokens` com
   `cached_input_tokens` contido (inferido do código-fonte — revalidar); ausente = `unknown`.
5. Orçamento do primeiro ensaio: **4 chamadas reais** (prova mínima + continuidade por
   provedor), sem repetição automática, prazo explícito [Livro p41].
6. Continuidade: provedor A extrai fatos de arquivo fictício → fundação grava com
   origem → provedor B, em sessão nova, lê **o artefato persistido** e cita seu
   identificador [Livro p41].

## Verificação
| Caso | Esperado |
|---|---|
| Chamada mínima real com palavra de controle aleatória (por provedor) | resposta real ligada à tarefa e à rota [Livro p41] |
| Continuidade A→B | B cita o identificador do artefato persistido |
| Adaptador desligado | contagem de despachos permanece **zero** (negar antes de iniciar) [Livro p42] |
| Projeto alheio / autenticação ausente / saída inválida (simulador rotulado) | falha sem chamada externa indevida |
| Dois adaptadores para o mesmo serviço | **não** atende "dois provedores" [Livro p42] |
| Falha da rota principal | alternativa autorizada executa ou tarefa fica bloqueada |

## Critério de aceite
Duas respostas reais e continuidade rastreável, com negativas corretas; consumo
medido ou "não observado"; simulação nunca contada como provedor [Livro p42–43].

## Estado padrão nesta skill (regra única: simulação nunca promove integração)
Chamadas reais consomem cota/créditos do titular: exigem autorização explícita e teto.
Enquanto isso: **R12 e R17 ficam `bloqueado`** com a condição "autorizar 4 chamadas reais
(2 por provedor) na rota X" e o comando pronto (adaptadores de
`assets/fundacao-kit/fundacao/adapters/cli.py`); **R13, R14 e R15 ficam parciais** — a
lógica (política de rotas, alternativa, normalização de consumo) está executada com o
simulador rotulado, e a parte real depende do R12.

## Diagnóstico rápido [Livro p43]
JSON inválido (diagnóstico misturado ou JSONL lido como objeto único); credencial
inesperada (inspecione a rota sem imprimir valores); resposta após timeout (reconcilie
antes de repetir); modelo rejeitado (não invente substituto nem mude o orçamento).

## Com o kit
`fundacao/adapters/` (`assets/fundacao-kit/fundacao/adapters/simulado.py`, `assets/fundacao-kit/fundacao/adapters/cli.py` com `ClaudeCLIProvider`/`CodexCLIProvider`
— código presente), `fundacao/core/processo.py` (executor de árvore com prazo e teto de saída),
`fundacao/core/routing.py`, `fundacao/core/usage.py`,
`registry/route_policy.json`. Testes: `tests/test_eventos_rotas.py`, `tests/test_configuracao_decidida.py`,
`tests/test_adaptadores_rotas.py` (linha de comando, entrada padrão, ambiente e tetos, com
`subprocess.run` substituído — nenhuma CLI de provedor é executada),
`tests/test_auditoria_1_5_0_execucao.py` (#9, #17), `tests/test_auditoria_1_7_6_recursos.py` (teto da
saída, com uma "CLI" de ensaio).
