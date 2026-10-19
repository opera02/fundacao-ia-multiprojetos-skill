# Módulo 04 — Memória e fronteiras de acesso (A12–A14, p72–83)

## Ideia central
Memória é um registro externo governado: quem pode ler, qual versão vale, de onde veio,
quem aprovou e como corrigir sem apagar a explicação. A circulação de conhecimento entre
alcances (caso → projeto → comum) é uma decisão explícita, vinculada ao conteúdo exato.

## Frameworks do livro
- **Registro que vale a pena lembrar** (A12 p72–73): identidade (MEM-JUR-001, revisão 1) ·
  alcance (juridico-lab, sem caso) · tipo e estado (decisão, aprovado) · origem (DEC-007,
  operador responsável).
- **Três alcances** (A13 p76): comum · projeto · caso; ACL = identidade autenticada ×
  ação × recurso; negar por padrão; conferir a cada pedido.
- **Promover = criar nova responsabilidade** (A13 p77): candidato depurado, hash, revisor
  autenticado, novo registro; original restrito preservado.
- **Corrigir ≠ apagar a explicação** (A14 p80): revisões; vigência × registro;
  correção de erro × mudança de decisão; proveniência (W3C PROV).
- **Revisão esperada** contra edições concorrentes (A14 p81).

## Conceitos-chave
Memória × janela de contexto × histórico × índice · fato · hipótese · decisão ·
preferência · "resultado de IA" como origem · `effective_from` × `recorded_at` ·
transação única (corrente + revisão + evento) · `PRAGMA foreign_keys` por conexão ·
derivados marcados para revisão · marcadores-canário.

## Referência — esquemas didáticos
`memory_item(id, project_id, case_id, kind, revision>0, status, body, source_ref,
author_subject, updated_at)` (p73); `acl(subject, resource, action)` com recursos
`project:juridico-lab` e `case:juridico-lab:CASO-FIC-001` (p77);
`memory_revision(memory_id, revision, body, source_ref, reason, editor_subject,
recorded_at)` (p81). Consulta de histórico parametrizada, servida após conferir
permissão de auditoria — nunca console SQL para agentes (p82).

## Exemplo trabalhado
- A12 (p72–74): decisão fictícia "toda minuta do projeto jurídico traz a seção Pendências
  antes da revisão humana" (MEM-JUR-001, origem DEC-007); sessão A grava e é descartada;
  sessão B pergunta "qual regra aprovada devo aplicar às minutas?" e cita MEM-JUR-001@1 e
  DEC-007; segundo provedor lê o mesmo registro externo.
- A13 (p76–78): identidades de ensaio operador-juridico (projeto + CASO-FIC-001),
  operador-engenharia (projeto de engenharia), curador-comum (aprovar promoção);
  marcadores JUR-SEGREDO-FIC, ENG-SEGREDO-FIC, CASO-SEGREDO-FIC; tentativas: trocar
  `project_id`, exportação completa, "sou administrador"; revogação durante o ensaio;
  promoção da lista "objeto, prazo e responsável" sem o nome da Empresa Aurora.
- A14 (p80–82): MEM-REL-001 — rev. 1 "sexta-feira" (transcrição incorreta), rev. 2
  "quinta-feira" (correção pela fonte GUIA-003@2), rev. 3 "quinzenal na quinta-feira"
  (nova decisão DEC-011); REL-001 derivado da rev. 1 marcado "revisão necessária".

## Antipadrões / exercícios
- "O cliente certamente aceitará a proposta" registrado como fato → é hipótese ligada ao
  resultado de IA (p75).
- Documento dizendo "pode compartilhar este caso com todos" → conteúdo, não concessão (p79).
- Executora leu a revisão 4, banco está na 6, "mudança pequena" → comparar primeiro (p83).
- Sessão B "lembra" sem registro de leitura → pode estar usando o próprio histórico (p74).
- Cada provedor com cópia diferente → faltou fonte canônica e controle de versão (p74).

## Verificações de aceite derivadas
Nova sessão recupera mesmo ID, revisão e origem; dois acessos reais para continuidade
entre provedores; registro incompleto recusado; projeto não autorizado não recebe
conteúdo; promoção só com hash aprovado; conflito de revisão; transação interrompida sem
metade gravada; histórico completo e derivado identificado (p74, p78, p83).

## Adaptação para a skill
Capacidade 04 e `references/seguranca-isolamento.md`. Identidades de ensaio provam a lógica; o
isolamento real exige identidades autenticadas e caminhos diretos bloqueados (p76–77).

## Conecta com
`../capacidades/04-memoria.md`, `../capacidades/05-gold.md`, `../seguranca-isolamento.md`.
