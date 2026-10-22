# Passagem — <tarefa> — <executor> — <data>

> Retorno de um executor delegado (subagente, outra sessão ou outro provedor) ao coordenador. É relato, não prova:
> o coordenador confere os arquivos e os hashes antes de registrar; arquivo ausente ou SHA-256 diferente do que está
> no disco = não registra e devolve. Sem segredo, dado pessoal nem trecho de caso. Apague os campos que não usar.

Papel e pedido (do pacote de delegação): | `run_id`: | Executor (agente, provedor e modelo lido do rastro):
Início e fim: | Situação: entregue · entregue com pendência · bloqueado (motivo e condição para seguir)

## Arquivos tocados
| Caminho real (relativo à raiz autorizada) | Ação (criado · alterado · apagado) | SHA-256 depois (ou "apagado") |
|---|---|---|
Ferramenta feita para a tarefa (script de comparação, invólucro) fica no projeto e entra nesta tabela; a da pasta
temporária da sessão some com ela e não pode ser citada como evidência.

## O que foi feito
| Item | Real ou simulado | Comando ou procedimento exato | Resultado e evidência (caminho, `run_id`, evento) |
|---|---|---|---|
Verificação que não rodou fica "não rodada", nunca "passou". Achado vem com a fonte (arquivo e linha, evento ou
`run_id`); hipótese fica separada de fato.

## O que não foi feito
| Item | Por quê | O que depende disso |
|---|---|---|
Perguntas abertas e quem decide cada uma:

## Armadilhas novas e recursos deixados
O que surpreendeu e vale para as próximas tarefas (entra na lista de armadilhas do pacote de delegação,
`references/capacidades/02-agentes-subagentes.md`, Implementação 1):
Processos, portas, pastas temporárias, travas e cópias de banco ainda abertos (ou "nenhum"):
