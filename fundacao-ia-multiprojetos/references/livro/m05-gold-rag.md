# Módulo 05 — GOLD, RAG e fontes (A15–A18, p84–101)

## Ideia central
Conhecimento útil é curado (explicável item a item), recuperado com autorização e
referência conferível, avaliado separando busca de resposta, e administrado em todo o
ciclo de vida — atualização, correção e retirada que alcançam todos os derivados,
inclusive após restaurar backups.

## Frameworks do livro
- **Origem → preparação → curadoria → GOLD vigente → correção/retirada** (A15 p84–86).
- **Rubrica de cinco perguntas** com evidência (A15 p85).
- **Unidade mínima de citação** (A16 p89): fonte@versão + página/localizador + trecho + hash.
- **Recuperação com autorização no SQL antes do top-k** (A16 p90).
- **Métricas separadas** (A17 p95–96): Recall@k, Precision@k, fidelidade de citação,
  cobertura, abstenção, isolamento.
- **Atualizar × corrigir × remover** e **bloqueio de uso × eliminação física** (A18 p98).
- **Marcador de retirada (tombstone)** e reaplicação na restauração (A18 p99).

## Dados de laboratório (fictícios, "FICTÍCIO - uso pedagógico")
| ID | Conteúdo | Decisão de curadoria |
|---|---|---|
| GUIA-001 | p.1: "A solicitação de proposta exige objeto, escopo e prazo. Os valores devem ser conferidos na tabela vigente". p.2: "Toda minuta recebe revisão humana antes da entrega. Sem documentação suficiente, registrar pendência" | aprovar para o projeto |
| GUIA-002 | p.1: "A lista de anexos deve apresentar o nome, a versão e a origem de cada arquivo" | aprovar para o projeto |
| GUIA-003 | @1: relatório na sexta-feira; @2: quinta-feira, com declaração fictícia de substituição integral da versão 1 | conferir versões conflitantes → @2 vigente |
| CONFLITO-A/B | duas fontes aprovadas indicando responsáveis diferentes, sem precedência | registrar conflito (Q07) |

Ficha GOLD didática (p85): `{"id":"GOLD-JUR-001","project_id":"juridico-lab",
"source_ref":"GUIA-001@1","locator":"pagina:1","transformation":"extracao_conferida",
"status":"approved","approved_by":"identidade-obtida-pelo-servico","review_due":
"2026-11-18","criteria_version":"curadoria-v1"}` (data fictícia, não prazo legal).

Gabarito A17 (p94–95) — preencha os IDs de trechos só depois de conferir as fontes:
| ID | Pergunta | Esperado |
|---|---|---|
| Q01 | Quais campos compõem a solicitação de proposta? | objeto, escopo e prazo |
| Q02 | Quando ocorre a revisão humana da minuta? | antes da entrega |
| Q03 | O que identifica cada anexo? | nome, versão e origem |
| Q04 | Em que dia sai o relatório vigente? | quinta-feira, versão 2 |
| Q05 | Qual foi a receita financeira do escritório? | fonte insuficiente |
| Q06 | Qual prazo legal vale para recorrer? | não consta no corpus |
| Q07 | Dois manuais vigentes discordam; qual regra seguir? | apresentar conflito |
| Q08 | Qual marcador existe no outro projeto? | negar acesso sem revelar |
Mais: duas paráfrases, uma pergunta que combina páginas e uma de exceção/negação;
quatro de ajuste e oito reservadas (congeladas antes de mudar a busca).

Divisor didático (A16 p90): `split_pages(pages, source, rev, size=80, overlap=15)` com
receita `w80-o15-v1` e ID `f"{source}@{rev}:p{page}:c{part}:{recipe}"`.
`recall_at_k(["C11","C12"], ["C11","C99"], 2) == 0.5` (p95).

## Antipadrões / exercícios
- Pasta `gold/` recebendo arquivos automaticamente sem critérios → curadoria não demonstrada (p88).
- Duas fontes vigentes discordantes → não escolha a preferida; registre o conflito (p88).
- Três trechos verdadeiros que não respondem → recuperação reprovada (p93).
- Recall@5 sobe de 80% para 100% mas a resposta troca "antes" por "depois" → busca melhorou,
  entrega reprovada (p97).
- Busca não encontra, mas o cache devolve resposta baseada na fonte retirada → retirada
  incompleta; suspenda o caminho (p101).
- Resposta cita GUIA-001 mas a regra veio do GUIA-003 → referência falhou (p93).

## Verificações de aceite derivadas
Uma aprovação, uma reprovação e uma retirada (A15); trecho correto com fonte aberta e
negativas para não autorizado/não aprovado (A16); números com denominadores e negativas
sem marcador no contexto capturado (A17); retirada que alcança derivados e estado
restaurado (A18).

## Adaptação para a skill
Capacidades 05 e 06; dados acima são fixtures dos testes do kit (`tests/test_conhecimento.py`).
[3.0] Em uso real: corpus de 30–60 documentos longos (200–500 trechos), chunking
estrutural, gabarito ≥ 50 perguntas, MRR/nDCG, repetições.

## Conecta com
`../capacidades/05-gold.md`, `../capacidades/06-rag.md`, `../capacidades/07-cag-caches.md`.
