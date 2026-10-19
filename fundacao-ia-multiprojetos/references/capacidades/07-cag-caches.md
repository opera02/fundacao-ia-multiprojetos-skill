# 07 — CAG e caches: estado KV, execução fria/quente, isolamento e invalidação

Requisitos: R26, R27, R28. Aulas: A19 [Livro p102–106], A20 [Livro p107–110];
3.0 §3.8. Trilha: avançada (CAG estrito) · essencial (invalidação de caches).

## Definição técnica adotada [Livro p102; Verificado 2026-10-18]
CAG segundo Chan et al., "Don't Do RAG: When Cache-Augmented Generation is All You
Need for Knowledge Tasks" (arXiv 2412.15605; repositório hhhuang/CAG, `kvcache.py`):
pré-carregar a coleção relevante no contexto, **calcular uma vez o estado KV** do
modelo (*prefill*) e reutilizá-lo em perguntas novas, **restaurando o estado-base**
após cada pergunta (truncar o que a pergunta acrescentou). O treino do modelo não muda;
a resposta é gerada de novo a cada pergunta.

| Mecanismo | O que reutiliza | Prova característica |
|---|---|---|
| RAG | trechos recuperados | busca e contexto por pergunta |
| **CAG adotado** | KV do conhecimento pré-carregado | estado real reutilizado em perguntas novas |
| Cache de prompts (provedor) | processamento de prefixo pelo serviço | contadores e regras do serviço |
| Cache de respostas | resposta pronta | retorno sem nova geração |

[3.0 R8.1] **R-CAG-estrito** (KV local) ≠ **R-prefix-cache** (provedor): o segundo
nunca satisfaz o primeiro. Dicionário Python, Redis ou cache de respostas não são CAG
[Livro p102].

## Fatos conferidos [Verificado 2026-10-18]
- Transformers (v5): `DynamicCache` é o padrão; reutilização de prefixo = *prefill*
  sob `torch.no_grad()` e `copy.deepcopy(cache)` por pergunta; `crop()` desfaz tokens;
  **não há orientação oficial para salvar o cache em disco** (persistência exige formato
  seguro e compatibilidade verificada; nunca pickle de origem não confiável) [Livro p104; 3.0 R8.2].
- O `kvcache.py` dos autores usa API antiga (`key_cache[i]`): fixe a versão ou adapte.
- Prompt caching Anthropic: `input_tokens` **exclui** tokens lidos/escritos em cache;
  TTL padrão 5 min (opção 1 h); escrita 1,25× (5 min) / 2× (1 h), leitura 0,1× (alguns
  modelos menos); **sem endpoint de limpeza manual** — expira pelas regras do serviço.

## Viabilidade antes de executar [Livro p103]
Identifique modelo e revisão, tokenizador, formato de conversa, biblioteca, licença,
origem dos pesos e acesso permitido. Conte o prefixo já formatado e reserve espaço
para pergunta e resposta. Estimativa didática (atenção completa):
`bytes_KV ≈ 2 × camadas × lote × tokens × cabeças_KV × dim_cabeça × bytes_por_elemento`
(ex. hipotético: 32 camadas, 8.192 tokens, 8 cabeças KV, dim 128, 2 bytes ≈ 1 GiB),
mais pesos, ativações e cópias. CPU pode servir para modelo pequeno; GPU não é exigência
universal. **Não baixe pesos sem autorização.** Corpus pequeno, estável e de permissões
homogêneas favorece CAG; grande, mutável ou com permissões variadas favorece RAG [Livro p103].

## Procedimento (script `scripts/cag_kv_demo.py`)
1. Congele corpus autorizado (hash, versão, lista de fontes) e formato do prefixo.
2. *Prefill* uma vez; registre comprimento, tamanho observado do KV e tempo.
3. Três perguntas novas, cada uma numa **ramificação** do cache-base; confirme que a
   segunda não herdou a primeira (cache-base com o mesmo comprimento) e **zero buscas**.
4. Repita **sem** reuso de KV nas mesmas condições; separe preparação, tempo por pergunta,
   memória e qualidade. Pergunta sem resposta → insuficiência.
5. Mude uma fonte: o cache antigo é **recusado** (impressão digital de modelo +
   tokenizador + corpus + prefixo + versões) e a nova coleção exige novo *prefill*.

```
python <skill>/scripts/cag_kv_demo.py --modelo <pasta-local-autorizada> --corpus g1.md g3.md \
  --pergunta "..." --pergunta "..." --pergunta "..." --testar-invalidacao --saida evidence/A19/cag.json
python <skill>/scripts/cag_kv_demo.py --modelo-sintetico ...   # mecanismo sem download; NÃO avalia qualidade
```
Evidências que valem: tokens processados no modo quente = só os da pergunta; o ramo
KV cresce a partir do prefixo (foi usado); cache-base intacto; saídas idênticas
quente × frio em decodificação gulosa; cache antigo recusado. Tempo menor isolado
**não** prova CAG [Livro p106]. Modelo sintético: "mecanismo executado", qualidade
não avaliada; R27 só fica validado com modelo real autorizado e avaliação de respostas.

## Invalidação e isolamento de todos os caches (R28) [Livro A20 p107–110]
- Um acerto de cache pode ser falha de segurança: confira a **autorização atual antes
  de qualquer hit** e versão/fontes/permissões antes de entregar.
- Chave de resposta inclui identidade autenticada, escopo, revisão de política e de
  corpus, provedor, modelo, versão do prompt, hash do contexto, configuração de geração
  e pergunta — metadados produzidos pelo servidor, nunca pelo modelo [Livro p108].
- `policy_rev`/`corpus_rev` por projeto: revogar incrementa a primeira; aprovar,
  atualizar ou retirar fonte incrementa a segunda → entradas antigas deixam de servir.
  TTL não resolve revogação [Livro p107–108]. Reprovar ou devolver a pendente uma fonte que
  estava aprovada também incrementa `corpus_rev`: sair do conjunto consumível muda o corpus.
- [Decisão; auditoria externa da 1.3.4] **Uma validação para todas as portas.** A leitura
  normal e a leitura por ID (`get_by_key`) usam o mesmo validador: projeto, identidade,
  revisões, prazo e estado de cada fonte citada (retirada; memória fora de vigência; versão GOLD
  não aprovada, não vigente ou com hash aprovado diferente do preparado). Acrescentar uma
  verificação só a uma porta reabre o problema.
- Protocolo: frio · quente · outro projeto · revogação (inclusive leitura por ID antigo)
  · fonte alterada · leitura antiga pausada antes da entrega (*stale read*) ·
  desativação sem trabalho/consumo residual · cache negativo após nova fonte ·
  cache semântico com pares "com/sem autorização" [Livro p108–109; 3.0 R8.5].
- Cache do provedor: impeça novos usos do contexto antigo e registre a limitação de
  eliminação remota; revogar não desfaz o que já foi entregue [Livro p110].

## Bloqueio padrão nesta skill
R26 pode ser documentado (decisão + viabilidade); R27 fica `em_desenvolvimento` com
"mecanismo executado (modelo sintético)" ou `bloqueado` até haver modelo local
autorizado (condição: autorizar pesos de modelo pequeno — ex.: 0,5–1,5 B parâmetros
[3.0 R8.2] — e registrar licença e origem); R28 é demonstrável já para caches de
resposta/recuperação com o kit.

## Com o kit
`fundacao/core/cache.py` (`response_key`, `ResponseCache.get/get_by_key/put`),
`fundacao/core/revisions.py`. Testes: `tests/test_cache_backup.py::TestCache`.
