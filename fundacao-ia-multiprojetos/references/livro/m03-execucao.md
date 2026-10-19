# Módulo 03 — Execução, provedores e ferramentas (A08–A11E, p40–71)

## Ideia central
A fundação executa trabalho real: dois provedores pelo mesmo contrato, coordenação
persistente com retomada, delegação revisada nas fontes e componentes administráveis
(ferramentas, hooks, MCP, skills, plugins) que podem ser descobertos, ligados,
desligados, atualizados e substituídos de forma verificável.

## Frameworks do livro
- **Contrato único, traduções diferentes** (A08 p40): o núcleo autoriza; o adaptador
  traduz e normaliza (`unknown` para ausentes).
- **Quadro de situações** (A08 p40–41): cota indisponível → registrar limite (retentar só
  com política); login ausente → sinalizar; saída inválida → guardar diagnóstico (uma
  correção limitada); componente desligado → negar antes da chamada.
- **Estados de etapa** (A09 p44) e **checkpoint mínimo** (p45).
- **Pacote de delegação e quatro papéis** (A10 p48).
- **Descoberta · instalação · ativação · saúde** (A11 p52); **ferramenta · skill ·
  plugin · servidor MCP** (A11 p52).
- **Donos de hook** (A11B p56): Git · Claude Code · orquestrador.
- **Capacidades MCP** (A11C p60): tools · resources · prompts; **versão do protocolo ×
  versão do SDK**.
- **Fonte canônica** de skills (A11D p64); **catálogo · instalação · componente · dados**
  em plugins (A11E p69).

## Conceitos-chave
Palavra de controle aleatória para provar chamada recente · JSONL × JSON · idempotência ·
reconciliação de recibo · prazo de posse · `waiting_human` · paralelismo comprovado por
sobreposição de horários · contador de despachos · `entrypoint` consultado só após
`enabled` · regressão · deduplicação por (hook, sessão, `tool_use_id`) · lançador
confiável que vincula identidade ao processo MCP · `disable-model-invocation` ·
escopo local/projeto/usuário.

## Antipadrões (dos exercícios)
- Claude respondeu pela assinatura e Codex só passou em simulação → integração com dois
  provedores **não** está pronta (p43).
- Executar de novo quando há recibo de sucesso e o estado diz `running` → reconciliar (p47).
- Três agentes concordam sem citar documento → não encerra a divergência (p51).
- Componente funciona chamado direto mas não está no inventário → falta integração
  operacional (p55).
- Hook PostToolUse "bloqueou" escrita → detectou depois do efeito (p59).
- `tools/list` retorna a ferramenta mas a chamada falha → descoberta demonstrada,
  operação não (p63).
- Skill jurídica funcionou no Claude Code → não prova uso sem adaptação em qualquer chat (p67).
- Plugin removido e relatórios produzidos continuam → remoção de software ≠ retirada de
  resultados (p71).

## Referência — exemplos nativos (conferir versão; ver `../fontes-verificadas.md`)
- Comandos mínimos (p41): `codex exec --json "Responda apenas: PRONTO"`;
  `claude -p "Responda apenas: PRONTO" --output-format json`.
- Subagente (p49): `.claude/agents/revisor-evidencias.md` com `name`, `description`,
  `tools: Read, Glob, Grep`.
- Hook (p56–57): PostToolUse, matcher `Write`, `type: command`, `args` com
  `${CLAUDE_PROJECT_DIR}`, `timeout: 5`. **Correção:** o filtro `if: "Write(...)"` não é
  consultado (regras de arquivo usam `Edit`/`Read`).
- Cliente MCP v2 (p61): `from mcp import Client, StdioServerParameters`;
  `async with Client(server, mode="legacy")`; `list_tools()`, `call_tool(...)`, `is_error`,
  `structured_content`.
- Skill (p65): `conferir-evidencias` com seções Quando usar · Procedimento · Aceite;
  `metadata.version` é convenção administrativa.
- Plugin (p68–69): `.claude-plugin/plugin.json` (`name`, `version`, `description`,
  `author`) e `.claude-plugin/marketplace.json` (`name`, `owner`, `plugins[{name, source}]`).

## Exemplo trabalhado (A10 p49)
`relato.md` diz que a entrega ocorreu em 12/04; `comprovante.txt` tem emissão em 13/04 e
não fala da entrega. O consolidador apressado escreve "entrega em 13 de abril"; o
revisor aponta a troca (data de emissão usada como data do evento) e a frase artificial
"houve confirmação por telefone", ausente das fontes — os dois defeitos conhecidos do ensaio.

## Verificações de aceite derivadas
A08 duas respostas reais + continuidade + negativas (despachos zero no desligado) ·
A09 retomada verificável e invalidação correta · A10 entrega atribuída, defeitos
detectados · A11 mesma interface nos dois projetos, desativação impede efeitos, 0.2.0 e
retorno · A11B disparo real, idempotência, desligamento · A11C protocolo real e negativa
pela rota MCP · A11D descoberta/execução reais, separação, atualização rastreável · A11E
ciclo de vida real e isolamento preservado.

## Adaptação para a skill
Capacidades 01, 02, 03 e 08. Chamadas reais exigem autorização de cota/custo; a skill
entrega comandos prontos; R12 e R17 ficam bloqueados até a execução real; R13–R15 ficam
parciais (lógica executada com simulador rotulado); R34 foi ensaiado localmente com o SDK
oficial (registro no host pendente); R36 fica pendente (instalar plugin altera o host).

## Conecta com
`../capacidades/01-orquestracao.md`, `../capacidades/02-agentes-subagentes.md`,
`../capacidades/03-provedores-modelos.md`, `../capacidades/08-ferramentas-hooks-mcp-skills-plugins.md`.
