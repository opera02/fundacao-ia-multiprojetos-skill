# Modelos, revisão e orçamento — desenho da 1.7.9

Preparo em 22/10/2026. Os nomes abaixo são candidatos, sem ativação nem consumo
autorizado. Disponibilidade comercial não prova acesso pela conta instalada.

## Referências vigentes

| ID Claude API | Entrada / saída por milhão de tokens | Candidato de tarefa |
|---|---|---|
| `claude-haiku-5-5` | a partir de US$0,10 / US$0,50 | classificação simples, depois de medir erros |
| `claude-sonnet-5-5` | US$2 / US$10 | comparação intermediária |
| `claude-opus-5-5` | US$4 / US$20 | análise complexa |
| `claude-fable-5-1` | US$10 / US$50 | hipótese de ganho em revisão difícil |

Preços são da API, não da assinatura; Haiku tem faixa de contexto que altera o
preço. Fonte: [modelos oficiais](https://platform.claude.com/docs/en/models/overview)
e [preços](https://claude.com/pricing), conferidos em 22/10/2026.

O Claude Code aceita `--model` e `--effort`. IDs completos evitam mudança silenciosa
de alias, mas conta e limites organizacionais podem mudar o esforço efetivo.
Fonte: [configuração oficial](https://code.claude.com/docs/en/model-config).
Fable pode consumir créditos conforme plano e saldo: acesso não implica gratuidade.
Fonte: [Fable no plano](https://support.claude.com/en/articles/15424964-claude-fable-models-on-your-plan).

`--max-budget-usd` limita a estimativa do cliente; uma chamada pode ultrapassá-la.
Reserva preventiva impede uma nova chamada sem saldo, mas não garante o valor da
fatura de uma chamada já iniciada. Usar margem e reconciliar consumo antes de
repetir. Fonte: [referência CLI](https://code.claude.com/docs/en/cli-reference).

## Política declarativa

O tipo de tarefa vem do fluxo autorizado. O conteúdo do documento não muda
permissões ou modelo. `/2` associa a cada tipo uma lista ordenada de alvos com
`route`, `provider_id`, `model` e `effort`; cada rota continua tendo autorização,
estado ligado/desligado e orçamento próprios. Dois provedores podem ocupar a
mesma rota sem confundir suas identidades. `/1` continua legível.

O evento distingue modelo/esforço pedidos do modelo observado. Ausência no rastro
permanece `unknown`; flag de comando não é prova de execução daquele modelo.
Toda tentativa que saiu conta, inclusive a que falhou ou foi interrompida.
Alternativa só para alvo previamente autorizado, sem repetição automática.

## Piloto proposto

Comparar três famílias de tarefa, com duas repetições e os mesmos dados fictícios:
extração estruturada com gabarito; conferência de ressalva/negação/número; análise
de defeito com prova negativa. Executar antes os scripts determinísticos que
resolvem a tarefa integralmente. Modelo local entra só nas famílias em que atingir
os critérios, nunca por ser gratuito.

Hipótese mínima: Qwen local, Haiku e Opus; três tarefas × duas repetições × três
modelos = 18 partidas, sendo 6 locais e 12 remotas. Fable e Sonnet ficam fora desse
primeiro piloto; acrescentá-los exige ampliar explicitamente a decisão. Definir
o gabarito e a tolerância antes de obter respostas: zero erro crítico de sigilo,
negação ou número; acerto não inferior ao limiar definido por tarefa. Registrar
latência, tokens, custo informado e lacunas separadamente. Esta amostra só decide
o próximo piloto, não demonstra generalização.

P7 é outro experimento: juiz recebe só pacote cego; concordância não substitui o
gabarito. O modelo Codex e seu esforço exatos ainda serão fixados com a decisão.
Não há evidência nesta preparação que autorize escolher o Codex mais caro ou
permita afirmar um teto monetário preventivo para a CLI dele.

## Decisões e estado

As quatro famílias de ensaio ficam em livros separados. A folha do projeto reúne
quantidade de partidas, modelo/esforço, regime de cobrança, teto financeiro,
repetição e condição de parada. Estimativa histórica de US$26 não é teto.
Nenhum livro real é aberto com autorização inventada; nenhum roteiro preparado
é execução. R13 permanece `implementado_inativo` até demonstração real aceita.
