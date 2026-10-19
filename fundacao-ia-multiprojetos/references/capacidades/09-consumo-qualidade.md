# 09 — Consumo e qualidade: orçamento, contexto seletivo e comparação com método

Requisitos: R37, R38, R39, R40. Aula: A21 [Livro p111–114]; 3.0 §3.8 (R8.3, R8.4,
R8.7, R8.8) e R1.3. Trilha: essencial.

## Três contas que não se misturam [Livro p111]
- **Tokens:** unidade do tokenizador do modelo; palavras/caracteres/bytes são
  aproximações. Registre o tokenizador; estimativa leva método e incerteza.
- **Tempo:** fronteiras claras — preparação, recuperação, compressão, *prefill*,
  primeiro token, conclusão. Local: `time.perf_counter` (diferença entre leituras);
  em GPU, sincronize antes de medir [Livro p111].
- **Custo:** depende do serviço, das categorias de uso e da conta; assinatura, API e
  execução local são regimes distintos; faturamento observado ≠ estimativa com
  tarifa oficial; indisponível = "não observado", nunca zero.

## Registro mínimo de execução [Livro p111]
`run_id`, `task_id`, `project_id`, `provider_id`, modelo/revisão, corpus, prompt,
variante, repetições, estado do cache e resultado; tokens normalizados sem dupla
contagem (novos · escritos em cache · lidos do cache · saída). Normalização por
provedor: `references/capacidades/03-provedores-modelos.md` e `fundacao/core/usage.py`.
Prompt caching (Anthropic, conferido em 18/10/2026): escrita 1,25× (5 min) / 2× (1 h),
leitura 0,1× (menos em alguns modelos); só compensa com prefixo **idêntico** —
compressão variável anula o ganho [3.0 R8.3].

## Onde economizar antes de acrescentar dependências [Livro p112]
Selecionar documentos pela finalidade; não reenviar todo o histórico; recuperar trechos
com localizadores; processamento convencional para somas/filtros/formatação; resumos de
retomada **com referências e pendências** (resumo que omite pendência vira erro);
limites por tarefa (consultas, tentativas, tamanho de saída, condição de parada);
modelo menor pode custar mais no total se exigir várias tentativas. CAG: contabilize
*prefill* e reconstrução; RAG: extração, indexação, recuperação e embeddings.

## Procedimento de comparação [Livro p113–114; 3.0 R8.8, R9.2]
1. Congele perguntas, corpus, critérios, parâmetros e **orçamento de chamadas**
   (pare ao atingir).
2. Variantes: contexto integral × seleção de trechos × seleção + compressão (e RAG/CAG
   quando reais). Alterne a ordem; ≥ 3 repetições no ensaio (CLIs não fixam temperatura
   nem semente → n ≥ 5 para conclusões) [3.0].
3. Registre mediana e dispersão de tempo, consumo por categoria e qualidade por
   pergunta; separe frio/quente; preserve falhas e repetições.
4. Compressão protege números, unidades, datas, negações, exceções, nomes de campos e
   identificadores de citação; teste a recuperação de um detalhe omitido a partir do
   original autorizado (R38).
5. Qualidade (correção, citações, cobertura, abstenção, isolamento) fica em colunas
   separadas do desempenho; redução de tokens que degrada critério essencial é rejeitada.
6. Decida manter · ajustar · retirar cada otimização, com condição de reavaliação;
   desative e confirme retorno ao comportamento anterior sem chamadas residuais.

Exemplo de leitura (números **hipotéticos** do livro): integral 12.000 tokens/11 de 12
aprovados; seleção 6.000/11 de 12 (−50%); seleção+compressão 3.600/10 de 12 (−40% sobre
a seleção, mais lento e perdeu um caso) → manter a seleção [Livro p112].

## Headroom e alegações externas
Repositório atual `headroomlabs-ai/headroom` (antes `chopratejas/headroom`); percentuais
do README são alegações dos mantenedores, não medições suas [Livro p113]. Situação não
verificada nesta skill [3.0 R8.7]. Se autorizado: versão fixada, ambiente isolado,
arquivos fictícios, telemetria/armazenamento/licença conferidos, ativar → medir →
recuperar o original → desativar. Compressão ≠ memória compartilhada.

## Orçamento que produz efeito (R39)
Teto por execução (chamadas e tempo), tentativas máximas por etapa e regra de
interrupção demonstrados com uma tarefa que **atingiria** o limite: a chamada
excedente não acontece e o evento fica registrado. Sob assinatura, o recurso escasso é
a cota (janelas de uso): registre consumo por execução e pare ao atingir limiar [3.0 R1.3].
Kit: `Budget(max_calls, max_seconds)`, `StepContext.charge_call`, teste
`test_orcamento_esgotado_interrompe_chamadas`.

## Bloqueios típicos
Sem contadores do provedor (aplicativo que não expõe) → medir texto visível não revela
instruções internas: marque "não observado" [Livro p111]. Sem chamadas autorizadas →
conclua medições locais (preparação, recuperação) e deixe consumo de geração pendente.
