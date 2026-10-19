# Glossário (síntese do Apêndice A e do texto; capítulos em aulas)

**ACL** — regras identidade × ação × recurso aplicadas antes de entregar dados ao modelo (A13).
**Adaptador** — traduz uma interface específica para o contrato comum; explicita o não equivalente (A04, A08).
**Agente** — instruções + modelo + ferramentas + estado num ciclo de trabalho (p2, A10).
**API / SDK / CLI** — interface entre programas / biblioteca para integrar / programa de terminal; regimes de acesso distintos (A03, A08).
**Atomicidade** — operação completa de forma coerente ou mantém o estado anterior (A06).
**Autenticação × autorização** — quem pede × o que pode fazer (A13).
**Bloqueado** — estado de requisito com impedimento e condição de resolução registrados (Ap. B).
**Busca lexical / híbrida** — por termos / combinação lexical+semântica com critérios explícitos (A16, Ap. A).
**CAG** — geração com conhecimento pré-carregado e reutilização do estado KV (A19).
**Cache de prompts × cache de respostas** — reaproveita processamento de prefixo no provedor × devolve saída pronta (A19–A20).
**Chave de cache** — fatores que tornam a reutilização válida (identidade, escopo, revisões, modelo, prompt, contexto) (A20).
**Checkpoint** — registro durável para outra execução prosseguir; não é backup nem confirmação de efeito externo (A09).
**Chunk (trecho)** — unidade indexada ligada a fonte, página e versão (A16).
**Citação (fidelidade de)** — fração de pares afirmação-citação sustentados (A17).
**Contrato** — entradas, saídas, erros, efeitos, permissões e versões esperados (Ap. A).
**Critério de aceite** — condição observável que decide se a entrega atende (Ap. A).
**Determinístico** — mesma transformação sob mesmas condições; usar em cálculos (Ap. A).
**Embedding / índice vetorial** — representação numérica / estrutura de vizinhos; semelhança não prova verdade (Ap. A).
**Estado de referência** — retrato recuperável de situação conhecida, com restauração ensaiada (A05).
**Evidência insuficiente** — registros não sustentam a conclusão; não é sucesso nem falha (Ap. A).
**Fonte canônica** — origem de referência; derivados apontam para sua versão (A11D, Ap. A).
**GOLD** — camada curada, validada e aprovada conforme critérios do usuário (A15).
**Hash** — impressão dos bytes; detecta diferença, não prova verdade, identidade nem consentimento (A05, A25).
**Harness** — mecanismos que envolvem o modelo: ferramentas, estado, contexto, limites, ciclo (Ap. A).
**Hook** — rotina disparada por evento; Git, CLI e orquestrador são mecanismos distintos (A11B).
**Idempotência** — repetir a mesma operação lógica não multiplica o efeito (A09, A11B, A30).
**Implementado e ativo / inativo** — demonstrado e habilitado / demonstrado e desabilitado de forma verificável (Ap. B).
**Ingestão** — entrada controlada com leitura, identificação, metadados e preparação (A16).
**Injeção de prompt** — conteúdo de entrada tentando virar instrução (A16, Ap. A).
**Invalidação** — impedir uso de derivado que deixou de valer (A20).
**Isolamento** — barreira entre contextos; pastas com nomes diferentes não bastam (A07, A13).
**KV cache / prefill** — chaves e valores da atenção / processamento do contexto inicial (A19).
**Markup × margem** — acréscimo sobre o custo × parcela do preço que sobra (A23).
**MCP** — protocolo cliente-servidor para ferramentas, recursos e prompts (A11C).
**Memória persistente / compartilhada** — registro externo entre sessões / acessível a agentes autorizados, não comum a todos os projetos (A12).
**Modelo × instância de projeto** — receita de criação × projeto concreto; migração é explícita (A07).
**Observabilidade** — compreender a operação por logs, métricas e rastros (A32).
**Orquestrador** — coordena ordem, dependências, estado, falhas, repetição e consolidação (A09).
**Plugin / conector** — pacote de distribuição / integração com serviço, com autenticação própria (A11E).
**Principal autenticado** — identidade reconhecida pelo sistema confiável; base da autorização (A07).
**Promoção** — mudança de alcance do conhecimento, aprovada sobre o conteúdo exato (A13).
**Proveniência** — origem e transformações de um dado (PROV-DM) (A14–A15).
**RAG** — gerar a partir de trechos recuperados de fontes (A16).
**Recall@k / Precision@k** — relevantes recuperados ÷ relevantes / ÷ k (A17).
**Regressão** — perda de comportamento aceito após mudança (A11, A29).
**Retry** — nova tentativa com condição, limite e tratamento do resultado anterior (Ap. A).
**Rollback × restauração** — retorno de código/estado; código e dados exigem procedimentos diferentes (A33).
**RPO / RTO** — perda máxima tolerada / tempo para recuperar (A35).
**Sandbox** — ambiente com restrições; venv não é sandbox (Ap. D).
**Skill** — pacote de instruções e recursos para competência reutilizável (A11D).
**Snapshot** — cópia de estado num momento, com limites de consistência (A35).
**Subagente** — agente delegado para escopo menor; devolve resultado, evidências e limites (A10).
**Teste de contrato / diferencial / metamórfico / negativo** — produtor×consumidor / mesma entrada em duas implementações / relação entre execuções / condição inválida rejeitada (A28, Ap. A).
**Token** — unidade do tokenizador; palavras são aproximação (p2, A21).
**Tombstone** — marcador de retirada que impede reaparecimento em consultas e restaurações (A18).
**TTL** — prazo de validade de entrada de cache; não resolve revogação (A20).
**Workflow** — fluxo de etapas que combina funções determinísticas, modelo e revisão humana (Ap. A).
