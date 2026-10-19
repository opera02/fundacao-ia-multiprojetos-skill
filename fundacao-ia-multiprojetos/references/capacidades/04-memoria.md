# 04 — Memória persistente: origem, versão, escopo, correção, concorrência

Requisitos: R16, R17, R18, R19, R20. Aulas: A12 [Livro p72–75], A13 [Livro p76–79],
A14 [Livro p80–83]; 3.0 §3.5. Trilha: essencial (A12, A13) · avançada (bitemporal).

## Objetivo operacional
Uma decisão registrada numa sessão é recuperada em outra sessão — e por outro
provedor autorizado — com identidade, revisão e origem, **por leitura real** do
serviço da fundação, nunca pelo histórico do chat.

## Conceitos que não se confundem [Livro p72]
Memória (registro persistente externo, com regras de leitura e alteração) · janela de
contexto · histórico de chat · índice de busca. Banco vetorial não traz governança;
memória pessoal de um aplicativo não se transfere para outro. [3.0 R5.1] Memórias
nativas (CLAUDE.md, AGENTS.md, memória dos apps) recebem só **resumos gerados** da
memória canônica da fundação.

## Modelo de registro
Campos mínimos [Livro p73]: `memory_id`, `project_id`, `case_id` opcional, tipo
(fato · hipótese · decisão · preferência · procedimento), estado, revisão (>0), texto,
origem (`source_ref`), responsável autenticado, horário UTC. [3.0 R5.2] Eixos
separados: tipo epistêmico × origem (humano/IA/documento) × estado — "a IA concluiu"
é origem, não selo de verdade [Livro p73]. Vigência (`effective_from`) ≠ registro
(`recorded_at`) [Livro p80].

## Implementação
1. Serviço com operações restritas **propor · aprovar · consultar · revisar ·
   histórico**; agentes nunca recebem acesso direto ao arquivo do banco [Livro p73].
2. Identidade da sessão autenticada/adaptador confiável; `project_id` é destino,
   não credencial; permissão aplicada **antes** de entregar conteúdo [Livro p73–74].
3. Proposta sem origem é recusada; repetição com o mesmo identificador de operação
   não duplica (chave de operação e gravação na mesma transação) [Livro p74].
4. Correção versionada: tabela de revisões; consulta normal = revisão vigente aprovada;
   histórico só para quem tem permissão de auditoria; correção de erro ≠ mudança de
   decisão [Livro p80–81].
5. Concorrência: **revisão esperada** — edição baseada em revisão antiga recebe
   conflito; a executora relê, compara e repropõe [Livro p81].
6. Estado corrente + revisão + evento numa transação (`BEGIN IMMEDIATE`, espera
   limitada); `PRAGMA foreign_keys = ON` em cada conexão [Livro p81].
7. Derivados: artefato que usou `memória@revisão` é marcado "revisão necessária"
   quando a memória muda; não é corrigido automaticamente [Livro p81].
8. Promoção ao comum: candidato **depurado** (sem nome de cliente/caso), justificativa,
   aprovação ligada ao **hash** do conteúdo exato por papel de curadoria, publicação
   como **novo** registro; o original restrito permanece; alteração após aprovação
   bloqueia a publicação; a IA não aprova a si mesma [Livro p77–78]. [Decisão; auditoria
   externa da 1.3.4] O candidato fica vinculado à revisão e ao hash da origem no pedido; na
   decisão, a origem é conferida de novo (dentro da transação): retirada, fora de vigência ou
   mudada desde o pedido impede a publicação, e retirar a origem encerra os candidatos pendentes.
   A retirada alcança a memória, as chaves `memória@revisão` e os derivados diretos e indiretos
   registrados a partir delas (só arestas exatas, sem coincidência de prefixo); o `init` aplica
   o mesmo alcance a memórias retiradas por kit anterior.
9. [3.0 R5.4] Anti-envenenamento: quarentena de propostas, origem "documento" nunca
   autoaprovada, teste negativo com documento que tenta se promover.
10. [3.0 R5.6] Exponha `memoria.consultar`/`memoria.propor` via MCP com ACL no
    servidor para que os dois provedores usem a mesma porta.

## Verificação
| Caso | Esperado |
|---|---|
| Gravar, encerrar sessão, nova sessão | mesmo ID, revisão e origem [Livro p74] |
| Segundo provedor | lê o **mesmo** registro externo; log do acesso real [Livro p73] |
| Proposta sem origem | recusada |
| Mesmo `op_id` repetido | sem duplicação |
| Marcadores `JUR-SEGREDO-FIC`/`ENG-SEGREDO-FIC`/`CASO-SEGREDO-FIC` | ausentes de projeto/caso não autorizados, inclusive em busca, resumo, prévia e contagem [Livro p77] |
| Troca de `project_id`, "sou administrador", exportação completa | negativa do serviço **antes** de qualquer chamada de geração [Livro p77] |
| Revogação durante o ensaio | memória do caso deixa de ser entregue; a do projeto continua |
| Revisão antiga / falha antes do commit | conflito / nada gravado pela metade [Livro p82] |
| Promoção | aprovada pelo hash; candidato alterado após aprovação recusado |

## Critério de aceite
Persistência só com leitura real em nova sessão; continuidade entre provedores só
com dois acessos reais registrados; transferência manual rotulada como tal [Livro p74].

## Bloqueios típicos
Sem segundo provedor autorizado → R17 `bloqueado` (persistência R16 pode ser
demonstrada). Sem contas/identidades reais do SO → R18 demonstrado como "lógica da
política"; isolamento real pendente (ver `references/seguranca-isolamento.md`).

## Com o kit
`fundacao/core/memory.py` (`MemoryService`). Testes: `tests/test_memoria.py` (8 casos).
