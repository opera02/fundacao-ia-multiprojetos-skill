# Ruflo — análise estática para a 1.7.9

Análise em 22/10/2026 da revisão `fac6d193ce481881655a16e512b799bdf4fb5a5c`.
Os cinco arquivos foram lidos como dados, sem instalação, importação nem execução.
O manifesto de pesquisa do projeto guarda URLs, tamanho e SHA-256; os cinco hashes
foram reconferidos nesta retomada. As conclusões cobrem essas fontes, não o repositório inteiro.

## O que o código mostra

| Fonte na revisão fixada | Comportamento observado | Consequência para a fundação |
|---|---|---|
| `v3/@claude-flow/cli/src/ruvector/model-router.ts`, linhas 2–35, 137–165 e 305–338 | Combina heurística lexical e amostragem Thompson por faixa de complexidade; mantém histórico local e admite caminho neural opcional. Registra mecanismo e identidade concreta separadamente. | O nome da técnica não demonstra economia nem qualidade. Precisamos de amostra por tarefa, modelo pedido/observado e origem da decisão. |
| `v3/@claude-flow/cli/src/ruvector/enhanced-model-router.ts`, linhas 386–551 | Tenta uma transformação determinística verificável antes de usar modelo; combina sinais de AST/texto. Descarta identidade concreta de outra faixa quando a faixa final muda. | Operações mecânicas verificáveis ficam em scripts. Uma mudança de rota também deve mudar a configuração concreta que será despachada. |
| `v3/@claude-flow/integration/src/multi-model-router.ts`, linhas 89–112, 203–237 e 493 em diante | Filtra capacidades/saúde e pontua candidatos; expõe regras, estimativas e orçamento. Inclui provedores locais e remotos. | Catálogo, estimativa e alerta não substituem reserva preventiva, autorização por projeto ou teto por tentativa. Valores de preços do código não são tabela comercial vigente. |
| `v3/@claude-flow/providers/src/provider-manager.ts`, linhas 173–175 e 279–318 | Alternativa em erro, com quantidade máxima de tentativas e eventos de sucesso/esgotamento. | Cada alternativa exige destino autorizado e conta no orçamento, inclusive a tentativa interrompida. |
| `plugins/ruflo-mods/hooks/route/route-task.ts`, linhas 25–77 | Regras lexicais escolhem papel de agente e confiança; palavras de revisão/segurança são sinais de classificação. | Texto recebido pode sugerir uma tarefa, mas não concede permissão nem decide sozinho provedor, custo ou escopo. |

Três limites aparecem nos corpos dos métodos, além dos comentários de desenho:

- `multi-model-router.ts:939–976` calcula tokens/custo estimados e devolve uma resposta
  construída localmente. Esse método não chama uma API: não serve como demonstração
  de integração real ou de economia medida. O roteamento em `route:495–542` é uma
  decisão separada do despacho.
- `provider-manager.ts:185–206` registra custo zero no caminho de streaming sem
  medi-lo ali. A fundação mantém ausência como desconhecida e não reutiliza esse
  zero como autorização de saldo.
- `enhanced-model-router.ts:395–417` pode recomendar o caminho determinístico sem
  conseguir ler o arquivo; o executor deve verificar a transformação. A fundação
  só declara a operação concluída com prova do resultado.

Fontes: [roteador](https://github.com/ruvnet/ruflo/blob/fac6d193ce481881655a16e512b799bdf4fb5a5c/v3/@claude-flow/cli/src/ruvector/model-router.ts),
[roteador ampliado](https://github.com/ruvnet/ruflo/blob/fac6d193ce481881655a16e512b799bdf4fb5a5c/v3/@claude-flow/cli/src/ruvector/enhanced-model-router.ts),
[múltiplos modelos](https://github.com/ruvnet/ruflo/blob/fac6d193ce481881655a16e512b799bdf4fb5a5c/v3/@claude-flow/integration/src/multi-model-router.ts),
[provedores](https://github.com/ruvnet/ruflo/blob/fac6d193ce481881655a16e512b799bdf4fb5a5c/v3/@claude-flow/providers/src/provider-manager.ts),
[papéis](https://github.com/ruvnet/ruflo/blob/fac6d193ce481881655a16e512b799bdf4fb5a5c/plugins/ruflo-mods/hooks/route/route-task.ts).

## Propostas e critério para adotar

| Proposta | Preparo na 1.7.9 | Evidência ainda necessária |
|---|---|---|
| R1: selecionar por tipo de tarefa autorizado | Política `/2` declarativa, com rota, provedor, modelo e esforço. `/1` continua legível. | Contratos e negativas locais; ensaio real antes de promover R13. |
| R2: executar trabalho mecânico por script | Preservar verificadores determinísticos; não chamar um modelo só para ler a saída de um comando. | Mesmo resultado e mesmas negativas na amostra autorizada. |
| R3: alternativa explícita e limitada | Ordem declarada, teto antes do despacho, custo ausente bloqueia a rota financeira. | Provas de reserva/concorrência e de recusa sem despacho. |
| R4: medir modelo local antes de usar | Piloto separado, corpus fictício e revisão humana dos erros críticos; Qwen já disponível não significa qualidade suficiente. | Precisão por tarefa, latência, tokens, ressalvas preservadas e limite de erro definido antes da rodada. |
| R5: adiar roteador aprendido/neural | Não incorporar dependências nem histórico de aprendizagem nesta versão. | Só reconsiderar se a política declarativa ficar insuficiente e houver dados aprovados de avaliação. |

As propostas são desenho e código autoral da fundação. Não foi copiado nem executado
código do Ruflo. Percentuais de economia e tempos anunciados pelos comentários não
foram medidos aqui. Nenhuma proposta liga rota nem autoriza consumo.
