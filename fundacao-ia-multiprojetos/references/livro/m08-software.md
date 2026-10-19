# Módulo 08 — Engenharia reversa de software (A26–A30, p133–158)

> CaixaSim é software didático original do livro (sem rede, sem IA, sem honorários
> automáticos). Serve como cenário de aceite das quatro finalidades: documentar,
> implementar outra versão, modernizar e integrar.

## Ideia central
Reutilizar a fundação num segundo domínio, sem herdar dados do primeiro, e tratar
engenharia reversa como quatro entregas distintas, cada uma com seu critério:
documentação contestável por evidências, implementação própria equivalente no conjunto
declarado, modernização que preserva a versão anterior e integração com limites claros.

## Contrato CaixaSim 1 (A26 p133–136)
Entrada (UTF-8, ≤ 65.536 bytes, chaves duplicadas rejeitadas): `{"schema":"caixasim/1",
"currency":"BRL","items":[{"id":"analise","qty":"2.5","unit_price":"80.00"},
{"id":"entrega","qty":"1","unit_price":"20.00"}]}` → saída `{"schema":"caixasim/1",
"currency":"BRL","lines":[{"id":"analise","amount":"200.00"},{"id":"entrega",
"amount":"20.00"}],"total":"220.00"}`.
Regras: 1–100 itens; `id` único `[A-Za-z0-9_-]{1,40}`; quantidade > 0, até 3 casas,
≤ 10.000; preço ≥ 0, até 2 casas, ≤ 1.000.000; campos extras rejeitados; vírgula
decimal e espaços externos normalizados; sem separador de milhar, sinal, expoente, zero
inicial desnecessário ou NaN; texto normalizado ≤ 16 caracteres; cada produto
arredondado a centavos por ROUND_HALF_UP; total = soma das linhas arredondadas;
precisão 28. CLI: sucesso → código 0 e resultado em stdout; erro → código 2 e
`{"error":{"code":...}}` em stderr, sem total parcial. Códigos: E_SCHEMA, E_ITEMS,
E_ID, E_DECIMAL, E_RANGE, E_SIZE, E_JSON, E_KEYS (p141).
O código integral da v1 está no livro (p134–136); materialize-o a partir do PDF.

## A27 — Compreender e documentar (p139–143)
Estados de conclusão: observação · evidência de implementação · inferência ·
desconhecido; intenção documentada confrontada com código e execução. Experimento
decisivo: duas linhas `0.005 × 1.00` → total **0.02**; uma linha `0.010 × 1.00` →
**0.01** (arredondamento por linha) — "reordenar preserva o total" vale; "dividir uma
linha preserva" não (p140, p143). `json` do Python aceita chaves repetidas por padrão;
o CaixaSim rejeita com E_KEYS (p140–141). Teste do revisor: afirmação falsa "a v1 aceita
desconto" → contradita pela rejeição de campo extra (E_SCHEMA) (p142–143). Saídas:
SPEC.md, ARCHITECTURE.md, EVIDENCE-MAP.csv, UNKNOWN.md, fixtures.

## A28 — Implementação própria (p144–148)
Compromisso de compatibilidade (SPEC-caixasim-1.0 congelada por hash) em oito regras;
algoritmo diferente: quantidade em milésimos e dinheiro em centavos,
`(produto + 500) // 1000` para metade-para-cima; `line_cents(2500, 8000)` → 200.00.
Três formas de conferir: exemplo conhecido · teste diferencial (60 casos válidos com
semente registrada) · teste metamórfico (reordenar → mesmo total; trocar ponto por vírgula
→ mesmo resultado; item gratuito novo → mesmo total; duplicar com IDs novos ≤ 100 itens
→ dobra). Negativos: quantidade "0", número sem aspas, chave duplicada. Concordância
entre dois programas não é autoridade sobre o requisito (p147). Total certo sem as
linhas → incompatível (p148).

## A29 — Modernizar (p149–153)
Refatorar (preserva v1) × acrescentar funcionalidade (cria v2). Módulos: `numbers.py`
(decimais/arredondamento; [3.0 R16.4] renomear para não colidir com o módulo padrão),
`domain.py`, `io_json.py`, `cli.py` (pacote `caixasim_next`); `python -m caixasim_next`. v2: `discount_percent`
obrigatório "0"–"100", até 2 casas; desconto = subtotal × % / 100 arredondado **uma vez**;
exemplo 220,00 − 22,00 = **198,00**; duas linhas de 0,01 com 50% → desconto 0,01, total
0,01; rejeitar "100.01"; v1 continua rejeitando `discount_percent` (p150–153). Retorno a
executável que só conhece v1 não processa pedidos v2 como v1 (p151).

## A30 — Integrar (p154–158)
Promover só o pacote técnico revisado a `components/caixasim/`; adaptador no projeto
jurídico traduz `services[].code/units/price` → `items[].id/qty/unit_price`; envia ao
motor apenas versão, moeda, itens e desconto; 880,00 com 10% → subtotal 880,00, desconto
88,00, total **792,00**; resultado `proposta-valor/1` com identificadores da tarefa,
`provider_id: local-python`, `status: pending_review` (p154–155). Validação de entrada e
saída (JSON Schema documenta; código aplica; `additionalProperties: false` explícito);
subprocesso com limite de 5 s; idempotência pelo estado (projeto, tarefa, entrada,
versão). Negativos: `price_kind: internal_cost` (R$ 660 não é preço de venda), resposta
inconsistente 79,20, contexto reversa-lab tentando o fluxo jurídico, campo extra com nome
de cliente, motor indisponível (sem preço inventado), desativação sem iniciar o motor (p156–158).
Exercício: mesmo total duas vezes, duas entregas criadas → idempotência **não** demonstrada (p158).

## Antipadrões
Executar cópia diferente da inspecionada; diagnóstico interpretado como resultado;
projeto "vazio" consultando o índice jurídico; mudar o programa para o teste passar
(aceitar número sem aspas); `domain.py` chamando a CLI por dentro (p138, p153).

## Adaptação para a skill
Cenário de aceite do Fluxo B (adaptação de software existente) e da reutilização do
modelo de projeto (R02, R04). [3.0 R16.1–R16.5] Nomeie as técnicas (golden master,
approval testing, propriedades, mutação, strangler fig, parallel run, anticorrupção);
ADRs; análise estática; sala limpa quando a licença exigir.

## Conecta com
`../fluxo-b-adaptar.md`, `scripts/caracterizar.py`, `../capacidades/08-ferramentas-hooks-mcp-skills-plugins.md` §1.
