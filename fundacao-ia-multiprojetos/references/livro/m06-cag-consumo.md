# Módulo 06 — CAG e consumo (A19–A21, p102–114)

## Ideia central
CAG, no sentido técnico adotado, é reutilizar o **estado KV** de um corpus
pré-processado; caches aceleram, mas nunca podem ultrapassar autorização nem servir
conhecimento retirado; otimizações são decididas por medição de consumo, tempo **e**
qualidade — não por alegações.

## Frameworks do livro
- **Quatro mecanismos que coexistem** (A19 p102): RAG · CAG · prompt caching · cache de
  respostas, cada um com sua prova característica.
- **Caber é condição concreta** (A19 p103): modelo, revisão, tokenizador, formato,
  licença, pesos, contagem do prefixo formatado, reserva para pergunta e resposta;
  fórmula de memória KV.
- **Protocolo frio · quente · inválido** (A20 p108–109) com sete testes.
- **Chave adequada por espécie de cache** (A20 p107): resposta · recuperação · KV de CAG ·
  prefixo do provedor, cada qual com mudança que exige recusa e ação seguinte.
- **Três contas que não se misturam** (A21 p111): tokens · tempo · custo.

## Conceitos-chave
Prefill · KV cache · cache hit/miss/inválido/negado · TTL (não resolve revogação) ·
`policy_revision`/`corpus_revision` · *stale read* · cache negativo · cache semântico ·
`perf_counter` · mediana e dispersão · redução relativa · Headroom (candidato).

## Referência
- Estimativa KV (p103): `bytes_KV ≈ 2 × camadas × lote × tokens × cabeças_KV ×
  dim_cabeça × bytes_elemento` (ex. hipotético ≈ 1 GiB para 32 camadas, 8.192 tokens,
  8 cabeças KV, dim 128, 2 bytes). Conferido nesta skill: a fórmula coincidiu com o
  tamanho observado do cache no Transformers 5.10.2 (modelo sintético).
- Chave de resposta (p108): `subject, scope, policy_rev, corpus_rev, provider_id,
  model_rev, prompt_rev, context_hash, generation, question` → SHA-256 do JSON canônico;
  metadados produzidos pelo servidor.
- Redução (p112): `reduction(before, after) = 1 − after/before` (None se base ≤ 0);
  `reduction(12000, 6000) == 0.5`; `reduction(6000, 3600) ≈ 0.4`.
- Tabela hipotética (p112): integral 12.000 tokens, 3,2 s, 11/12 · seleção 6.000, 2,3 s,
  11/12 · seleção + compressão 3.600, 2,6 s, 10/12 → manter a seleção.
- Campos Anthropic (p111; conferido): `input_tokens` não inclui cache; total = soma das
  três categorias.

## Antipadrões / exercícios
- Primeira pergunta 5 s, segunda 1 s → não prova CAG (p106).
- TTL de 1 h, autorização revogada há 1 min → **não** pode haver hit (p110).
- Ferramenta promete 90%, ensaio mede 12% e é mais lento → entra 12%, com condições (p114).
- `cag-cache.bin` existe → não prova uso do estado; resposta instantânea por casamento de
  pergunta = cache de respostas; corpus reprocessado sem reuso = contexto longo (p105).
- Baixar o modelo do README acadêmico automaticamente (p103).

## Exemplo trabalhado (A19 p104)
Congelar os guias aprovados (permissões homogêneas) → prefixo com instruções, textos e
localizadores → prefill único → três perguntas (campos da proposta, revisão humana, dia
do relatório) em ramificações do cache-base → sem reuso nas mesmas condições → pergunta
sem suporte → mudança de fonte recusa o cache antigo e exige nova pré-carga.

## Verificações de aceite derivadas
R27 só com perguntas distintas e geração real a partir do estado pré-carregado; negativa
de cache incompatível/desatualizado/não autorizado; R28 com hit/miss/inválido/negado
registrados separadamente; decisão de otimização com dados brutos e denominadores.

## Adaptação para a skill
Capacidades 07 e 09; `scripts/cag_kv_demo.py` executa o mecanismo (modo sintético sem
download) e o kit implementa a invalidação de caches de resposta/recuperação.

## Conecta com
`../capacidades/07-cag-caches.md`, `../capacidades/09-consumo-qualidade.md`,
`../fontes-verificadas.md` §5.
