# Padrões e técnicas do livro (com proposta 3.0)

## Evidência em quatro níveis
**Quando usar**: em toda afirmação de relatório. **Como**: classifique em documentado ·
código presente · executado · validado e cite o registro. **Trade-offs**: mais trabalho
de registro; evita arquitetura baseada em instalações imaginárias (A01).

## Prova negativa com marcador-canário
**Quando**: qualquer fronteira (projeto, caso, cache, componente, hook, MCP). **Como**:
dados fictícios com marcadores únicos; tente acessar pela mesma função de leitura do
sistema; confirme ausência em saída, contexto e logs. **Trade-offs**: exige captura
controlada do contexto (só com dados fictícios) (A07, A13, A20).

## Estado de referência com restauração ensaiada
**Quando**: antes de alterar estado existente. **Como**: abrangência → identidade única →
Git + arquivos fora do Git + backup SQLite + receita de ambiente → restaurar em pasta nova
→ prova negativa. **Trade-offs**: tempo de cópia; revela cedo lacunas de abrangência (A05).

## Modelo de projeto com lista positiva e criação atômica
**Quando**: criar projetos. **Como**: arquivos permitidos explícitos; pasta temporária →
validação → instalação; colisão informada sem sobrescrever. **Trade-offs**: modelo
mínimo exige configurar cada projeto (A07).

## Contrato único + adaptadores
**Quando**: provedores, ferramentas, legado. **Como**: o núcleo fala o contrato; o
adaptador traduz e normaliza; capacidades não equivalentes ficam explícitas.
**Trade-offs**: camada a mais; troca de fornecedor sem reescrever fluxos (A04, A08, A30).

## Coordenação persistente com checkpoints
**Quando**: tarefas com etapas, falhas e retomada. **Como**: fluxo como dados, máquina de
estados, hashes de entrada, transações curtas, recibo + reconciliação, limites.
**Trade-offs**: manter motor próprio custa; frameworks duráveis (DBOS, LangGraph) trocam
esse custo por dependência [3.0] (A09).

## Delegação com revisão nas fontes
**Quando**: trabalho divisível. **Como**: pacote de delegação por papel; paralelismo só
entre independentes; revisor recebe originais; defeitos plantados. **Trade-offs**:
multiagente consome mais tokens; sem ganho medido, use fluxo simples (A10).

## Componente com ciclo de vida
**Quando**: qualquer ferramenta reutilizável. **Como**: registro próprio; descobrir sem
executar; checar `enabled` antes de importar; contador de despachos; 0.1.0 → 0.2.0 → retorno.
**Trade-offs**: burocracia leve; desligamento verificável por todas as rotas (A11, A34).

## Hook preventivo + observador
**Quando**: garantias determinísticas. **Como**: `permissions.deny` + PreToolUse que nega;
PostToolUse só para auditoria idempotente. **Trade-offs**: hooks não são fronteira
completa; shell precisa de sandbox (A11B; 3.0 R4.1).

## Memória com revisão esperada e promoção por hash
**Quando**: conhecimento entre sessões e projetos. **Como**: propor/aprovar/consultar;
revisão vigente; conflito por revisão esperada; promoção cria novo registro aprovado
pelo hash. **Trade-offs**: aprovação humana adiciona espera (A12–A14).

## Curadoria GOLD com rubrica de cinco critérios
**Quando**: conhecimento consumido por IAs. **Como**: origem · fidelidade · vigência ·
acesso · finalidade, cada um com evidência; aprovação do hash publicado. **Trade-offs**:
custo de revisão proporcional ao risco (A15).

## RAG lexical autorizado e avaliado
**Quando**: perguntas sobre documentos. **Como**: trechos com ID/página/hash; FTS5 por
projeto; ACL no SQL antes do top-k; gabarito; métricas separadas. **Trade-offs**: lexical
falha em sinônimos → expansão rastreável ou híbrida medida (A16–A17).

## Retirada por marcador e reaplicação
**Quando**: atualizar, corrigir ou remover fonte. **Como**: marcador primeiro; derivados
transitivos; limpeza retomável; registro protegido reaplicado na restauração.
**Trade-offs**: invalidação ampla é simples e cara; por recurso é eficiente e complexa (A18, A20).

## CAG estrito
**Quando**: corpus pequeno, estável, permissões homogêneas, modelo local autorizado.
**Como**: prefill único → ramificações do cache-base → comparação sem reuso → recusa de
cache desatualizado. **Trade-offs**: memória e reconstrução a cada mudança do corpus (A19).

## Comparação de consumo com método
**Quando**: decidir otimizações. **Como**: congelar condições; alternar ordem; repetir;
mediana e dispersão; qualidade separada; preservar falhas. **Trade-offs**: rodadas pequenas
mostram variação, não conclusões estatísticas (A21).

## Golden master + comparação antes/depois
**Quando**: adaptar ou modernizar software existente. **Como**: gravar comportamento
atual para entradas conhecidas (inclusive erros) → mudar pouco → comparar → classificar
divergência. **Trade-offs**: só cobre as entradas gravadas; complemente com propriedades
(A26–A29; 3.0 R16.1; `scripts/caracterizar.py`).

## Atualização em seis etapas
**Quando**: mudar versão de dependência, adaptador, skill, modelo. **Como**: preparar ·
ler · isolar · comparar · decidir · promover/retornar. **Trade-offs**: mais lenta que
"atualizar tudo"; permite atribuir causa de regressão (A33).
