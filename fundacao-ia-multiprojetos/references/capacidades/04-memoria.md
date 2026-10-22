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
   histórico só para quem tem permissão de auditoria (memória de caso: auditoria no caso
   [varredura da 1.4.5, #15]); correção de erro ≠ mudança de decisão [Livro p80–81].
5. Concorrência: **revisão esperada** — edição baseada em revisão antiga recebe
   conflito; a executora relê, compara e repropõe [Livro p81]. Aprovação concorrente
   obsoleta também falha com `RevisionConflict` [auditoria sobre a 1.4.1, A10].
6. Estado corrente + revisão + evento numa transação (`BEGIN IMMEDIATE`, espera
   limitada); `PRAGMA foreign_keys = ON` em cada conexão [Livro p81].
7. Derivados: artefato que usou `memória@revisão` é marcado "revisão necessária"
   quando a memória muda; não é corrigido automaticamente [Livro p81]. O derivado
   registrado é artefato (memória e fonte GOLD, não): de memória para memória, só pela
   promoção [varredura da 1.4.5, #7].
8. Promoção ao comum: candidato **depurado** (sem nome de cliente/caso), justificativa,
   aprovação ligada ao **hash** do conteúdo exato por papel de curadoria, publicação
   como **novo** registro; o original restrito permanece; alteração após aprovação
   bloqueia a publicação; a IA não aprova a si mesma [Livro p77–78]. [Decisão; auditoria
   externa da 1.3.4] O candidato fica vinculado à revisão e ao hash da origem no pedido; na
   decisão, a origem é conferida de novo (dentro da transação): retirada, fora de vigência ou
   mudada desde o pedido impede a publicação, e retirar a origem encerra os candidatos pendentes.
   A retirada alcança a memória, as chaves `memória@revisão` e os derivados diretos e indiretos
   registrados a partir delas (só arestas exatas, sem coincidência de prefixo), sem sair do
   escopo de quem retira, salvo a publicação aprovada [varredura da 1.4.5, #7]; o `init` aplica
   o mesmo alcance a memórias retiradas por kit anterior.
9. [3.0 R5.4] Anti-envenenamento: quarentena de propostas, origem "documento" nunca
   autoaprovada, teste negativo com documento que tenta se promover.
10. [3.0 R5.6] Exponha `memoria.consultar`/`memoria.propor` via MCP com ACL no
    servidor para que os dois provedores usem a mesma porta.

## Lições: memória de procedimento do projeto
[Decisão; harness2, P3 — método adaptado de Harness² (arXiv:2610.14224, github.com/google-research/harness2,
commit 1cfe254, Apache-2.0); texto próprio.] Lição é o que uma tarefa ensinou sobre **como trabalhar** no projeto.
1. Fica numa memória do tipo `procedimento`, no escopo do **projeto**, nunca no do caso. O texto traz gatilho (a
   forma da situação, não os fatos dela), lição (uma ação que se pode conferir), evidência e confiança (alta ·
   média · baixa); o `source_ref` aponta a evidência (o `run_id` ou o caminho dela).
2. Nunca leva fato do caso: nome, número, data, trecho ou conclusão ficam no caso. Lição que só se entende com um
   fato do caso não é do projeto.
3. No máximo uma por tarefa, e "SEM_ENTRADA" vale (`assets/templates/RELATORIO-FINAL.md` §5b). Lição apoiada só em
   mudanças de veredito "confundido" é palpite: confiança no máximo média.
4. Entra como **proposta**, e quem propôs não aprova (itens 8 e 9 acima).
5. Antes de uma tarefa nova, consulte as lições aprovadas do projeto e trate cada uma como **hipótese** a reconferir
   nessa tarefa, não como fato.
6. Para a camada comum, só pela promoção curada do fluxo C (C7): candidato depurado e aprovação pelo hash.

## Memória automática do host
[Decisão; everything-claude-code, proposta 3 — ideia adaptada; texto próprio.] O Claude Code guarda notas que ele
mesmo escreve numa pasta por repositório Git (`~/.claude/projects/<pasta>/memory/`); fora de um repositório, vale a
pasta onde a sessão abriu. O índice `MEMORY.md` entra no início de toda sessão aberta ali (as primeiras 200 linhas
ou 25 KB); a memória fica só nesta máquina e não é carregada nos subagentes, salvo numa bifurcação (*fork*) da
conversa. Desliga com `autoMemoryEnabled: false` nas configurações ou com `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`
[Verificado 2026-10-21; code.claude.com/docs/en/memory]. Como as sessões da fundação abrem na raiz, seja ela
repositório Git ou não, **a memória automática é uma só para todos os projetos da raiz**.
- Nela só entra lição de operação da fundação (como rodar, armadilha de ferramenta), sem nome, número, fato ou
  trecho de projeto ou de caso. Lição de um projeto fica no projeto (§Lições).
- O que ela diz é contexto, não autorização nem prova: confira no estado real antes de agir, como com a RETOMADA.
- Lição extraída de uma sessão é proposta, nunca aprovada por quem a extraiu (item 8 acima). Ferramenta de
  "aprendizado automático" que grava skill, regra ou memória no perfil do usuário não é adotada: valeria para todos
  os projetos.
- Desligá-la na sessão de dados reais é decisão do titular, no preparo do host.

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
`fundacao/core/memory.py` (`MemoryService`). Testes: `tests/test_memoria.py` (8 casos),
`tests/test_auditoria_1_5_0_dados.py` (A10; #7, #15, #19).
