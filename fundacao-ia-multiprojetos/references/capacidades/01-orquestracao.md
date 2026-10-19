# 01 — Orquestração: tarefas, dependências, estados, checkpoints e retomada

Requisitos: R05, R06, R07, R08 (e R39 orçamento). Aulas: A04B [Livro p24–27], A09
[Livro p44–47]. Trilha: essencial (workflow durável) · avançada (orquestrador próprio
como exercício) [3.0 R3.2].

## Objetivo operacional
O andamento existe **fora da conversa**: o sistema sabe o que terminou, o que
depende do quê, o que falhou e o que precisa de decisão humana, e retoma sem
repetir efeitos já confirmados.

## Escolha fundamentada (R05)
- Compare ao menos duas abordagens viáveis no ambiente real: núcleo modular próprio
  (kit), LangGraph com persistência, DBOS em SQLite, CrewAI Flows, Microsoft Agent
  Framework (sucessor de AutoGen e Semantic Kernel), Pydantic AI, OpenAI Agents SDK,
  Claude Agent SDK [Livro p24–25; 3.0 R3.1]. Temporal/Restate/Inngest/Prefect ficam
  fora do escopo local [3.0 R3.1].
- Núcleo próprio não elimina orquestração: transfere à equipe a manutenção de estado,
  repetição, persistência e concorrência — compare esse custo com o de aprender e
  manter um framework [Livro p25]. Para não programadores, manter um motor de
  workflow é o maior custo oculto [3.0 §1].
- Prove com o mesmo cenário nas duas: execução normal; **falha após gravar o
  artefato e antes de confirmar**; retomada sem duplicar; troca de adaptador; projeto
  sem acesso [Livro p25]. Registre fonte oficial, versão/commit e licença datados.

## Implementação (R06–R08)
1. **Fluxo como dados:** etapas, dependências, critérios de saída e versão do fluxo;
   o validador rejeita dependência inexistente e ciclos [Livro p45].
2. **Máquina de estados formal:** `pending → running → succeeded|failed|waiting_human|cancelled`,
   com tabela de transições permitidas e teste das proibidas [Livro p44; 3.0 R2.2].
   Estado de tarefa ≠ estado de componente do inventário.
3. **Checkpoint por etapa:** `run_id`, `task_id`, `project_id`, etapa, tentativa,
   versão do fluxo, hashes das entradas, referência e hash da saída, resultado da
   validação — não o histórico do chat [Livro p45].
4. **Transações curtas:** reserve a etapa, libere a transação, faça o trabalho
   demorado, registre o resultado; SQLite tem um escritor por vez; não segure a
   transação durante chamada de modelo [Livro p45–46].
5. **Idempotência e reconciliação:** mesma chave → reutiliza resultado validado;
   efeito externo de desfecho incerto é **reconciliado** pelo recibo antes de
   repetir; não prometa execução única a serviços externos [Livro p45].
6. **Limites:** tentativas por etapa, prazo de posse (*lease*) para detectar
   trabalhador abandonado, orçamento de chamadas e de tempo; erros permanentes
   (login ausente, entrada inválida, permissão negada) não são repetidos [Livro p47].
7. **Decisão humana:** etapa `waiting_human` apresenta opções concretas; a decisão
   fica ligada ao hash do conteúdo apresentado; tarefas independentes continuam
   [Livro p46; R07].
8. **Eventos na mesma transação** (outbox) para reconstruir a execução [3.0 R2.7].

## Verificação
| Caso | Esperado |
|---|---|
| Normal | ordem correta; transições registradas; contagem de execuções = 1 por etapa |
| Interrupção após extração (estado confirmado) | retomada pelo mesmo `run_id` não reexecuta a extração |
| Saída gravada sem confirmação | reconciliação pelo recibo/hash, sem reexecutar |
| Fonte alterada | invalida só as etapas derivadas daquela entrada |
| Dependência falhou | etapas dependentes não iniciam |
| Erro transitório | repete até o limite e para |
| Orçamento esgotado | interrompe antes da chamada excedente; evento registrado |
| Decisão humana | conteúdo alterado invalida a aprovação; independentes seguem |
| Projeto alheio | negativa antes de qualquer acesso |

## Critério de aceite
Retomada verificável com contagem de execuções; invalidação correta; nenhuma etapa
avança com dependência inválida; simulações rotuladas e uma execução curta real por
adaptador **somente** dentro do orçamento autorizado [Livro p46].

## Bloqueios típicos
Sem provedor real autorizado → valide a coordenação com simulador rotulado; R06–R08
podem ser demonstrados localmente; a parte "execução real" do adaptador fica pendente.

## Antipadrões
Lista com caixas marcadas pela IA chamada de orquestrador; "arquivo de saída existe"
como critério de sucesso; repetir vinte vezes um erro permanente; matar processos
desconhecidos para testar interrupção (use modo de teste) [Livro p44–47].

## Com o kit
`fundacao/core/tasks.py` (`Coordinator`, `StepDef`, `Budget`, `NeedsHuman`,
`TransientError`, `PermanentError`, modo `interrupt=(etapa,'before_commit'|'after_commit')`).
Testes: `tests/test_orquestracao.py` (10 casos).
