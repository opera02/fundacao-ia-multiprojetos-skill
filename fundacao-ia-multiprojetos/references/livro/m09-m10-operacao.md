# Módulos 09–10 — Conversa, acompanhamento, manutenção e autonomia (A31–A36, p159–181)

## Ideia central
A fundação é operada por conversa sem perder rastreabilidade, auditada pelos próprios
registros, atualizada com retorno, desligada de verdade, restaurada sem ressuscitar o
que foi retirado e avaliada por evidências — com o usuário dirigindo e avaliando o trabalho.

## Frameworks do livro
- **Interação esperada** (A31 p159): seleção do projeto autorizado → solicitação com
  artefatos e tarefa → acompanhamento com etapa/horário → retomada pelo `run_id` correto.
- **Logs · métricas · rastros** e **painel de cinco blocos** (A32 p163–164).
- **Quatro contratos a comparar na atualização** (A33 p167) e **seis etapas**
  (preparar, ler, isolar, comparar, decidir, promover/retornar) (p168).
- **Instalação · habilitação · saúde · autorização** e **desativação completa** (A34 p170).
- **Conjunto de recuperação; RPO e RTO; armadilha da fonte revogada** (A35 p174–175).
- **Duas avaliações independentes** e **quatro situações finais** (A36 p178–179).

## Conceitos-chave
Estado de navegação × escopo imutável da tarefa · transparência útil (fontes, operações,
resultados, critérios, limites) · denominador correto · cauda de latência · versionamento
semântico · venv recriável · *drain* · fallback autorizado · reconciliação de efeitos
posteriores ao snapshot.

## Exemplos e exercícios (viram verificações)
- Revisão iniciada em juridico-lab, usuário muda para reversa-lab e pergunta "ficou
  pronto?" → consultar só execução acessível, sem anexar o contrato ao projeto de software;
  na dúvida, mostrar identificadores e pedir escolha curta (p162).
- Painel com 95% de sucesso excluindo interrompidas → denominador incompleto (p166).
- Atualização mantém cálculos mas retoma tarefas concluídas como pendentes → reprovar (p169).
- Compressor removido da interface continua observando pasta → desativação incompleta (p173).
- Após restaurar, tarefa pendente com confirmação posterior de entrega → reconciliar antes
  de executar (p177).
- Matriz "100%" com segundo provedor por cópia manual → reclassificar como transferência
  manual; manter integração pendente; não repetir fluxos que não dependem disso (p181).

## Avaliação final (A36 p179–180)
Situação 1: dois provedores + memória externa + negativa entre projetos + correção do
registro. Situação 2: os dois projetos (petição, honorários, proposta, contrato;
documentação, implementação própria, modernização, integração). Situação 3: desativar,
substituir, restaurar e retomar. Situação 4: `pesquisa-lab` pelo modelo, sem copiar
dados, com tarefa curta. Rubrica do administrador: pedido de trabalho (entrada,
resultado, limites, critérios) · evidência · isolamento (por que `project_id` no prompt
não autoriza) · custo e qualidade (escolha com medidas comparáveis) · recuperação
(retomar sem repetir efeito).

## Adaptação para a skill
Fluxo C (C4, C6, C8–C11) e capacidades 10 e 11. [Decisão] O "registro de aprendizagem"
vira registro de decisões e entendimento demonstrados pelo usuário (R51), sempre
descritivo. "Devolva ao tutor" → relatório ao usuário com evidência e próximo passo.
Ordem 3.0: backup (A35) antes de atualização (A33); auditoria com avaliador independente.

## Conecta com
`../fluxo-c-operar.md`, `../capacidades/10-observabilidade-conversa.md`,
`../capacidades/11-manutencao-recuperacao.md`.
