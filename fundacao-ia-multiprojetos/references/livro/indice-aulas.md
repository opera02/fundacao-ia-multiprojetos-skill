# Índice do livro por aula (41 aulas, 10 módulos, apêndices)

Livro: *Fundação de IA Multiprojetos — Conceber, construir e administrar uma base
reutilizável de inteligência artificial*, edição 2.0 (18/10/2026, PDF de 219 páginas).
Páginas = numeração impressa do PDF. "Artefatos" = entregas pedidas no prompt executor
da aula (adaptadas pela skill às capacidades e fluxos). Uso: localizar a origem de uma
regra e a síntese do módulo: `references/livro/m01-diagnostico.md`, `references/livro/m02-nucleo.md`, `references/livro/m03-execucao.md`,
`references/livro/m04-memoria.md`, `references/livro/m05-gold-rag.md`, `references/livro/m06-cag-consumo.md`, `references/livro/m07-juridico.md`,
`references/livro/m08-software.md`, `references/livro/m09-m10-operacao.md`, `references/livro/apendices.md`; correções: `references/livro/correcoes-3.0.md`.

| Mód. | Aula | Título | Páginas | Conquista (resumo) | Artefatos da aula | Requisitos |
|---|---|---|---|---|---|---|
| 01 | A01 | Inspecionar o ambiente local | 8–11 | diagnóstico verificável sem alterar nada | RELATORIO-DIAGNOSTICO, inventario.json, EVIDENCIAS, RETOMADA | — (3.0: recebe requisito) |
| 01 | A02 | Ler e classificar o projeto existente | 12–15 | mapa de funcionamento da solicitação à entrega | MAPA-FUNCIONAL, INVENTARIO-COMPONENTES.json, REGRAS-A-PRESERVAR | — (3.0: recebe requisito) |
| 01 | A03 | Conferir recursos, permissões e custos | 16–19 | mapa de acesso, permissões e orçamento | ACESSOS.json, ORCAMENTO, PERMISSOES | R03, R12, R15 |
| 01 | A04 | Comparar arquiteturas e escolher o software de estudo | 20–23 | direção de construção e contratos | ARQUITETURA, DECISAO-001, MATRIZ-ALTERNATIVAS | R01, R05 |
| 01 | A04B | Pesquisar frameworks no GitHub | 24–27 | escolha de orquestração por evidência e protótipo | PESQUISA-FRAMEWORKS, MATRIZ-COMPARATIVA, 2 protótipos, DECISAO-002 | R03, R05 |
| 02 | A05 | Criar e conferir o estado de referência | 28–31 | ponto de retorno com restauração demonstrada | manifesto, cópia, instrução de restauração | R44 |
| 02 | A06 | Criar o núcleo mínimo e o inventário | 32–35 | núcleo que reconhece projetos e persiste tarefas | pacote, `python -m fundacao status`, inventário, contratos | R01, R02, R04 |
| 02 | A07 | Criar um projeto a partir do modelo | 36–39 | dois projetos pelo mesmo modelo, isolados | gerador, modelo versionado, 2 instâncias, contrato de acesso | R02, R03, R44, R45 |
| 03 | A08 | Demonstrar duas integrações funcionais | 40–43 | respostas reais de 2 provedores + continuidade | adaptadores, contratos, orçamento | R12–R15, R39 |
| 03 | A09 | Coordenar e retomar tarefas | 44–47 | execução em etapas com interrupção e retomada | coordenador, formato do fluxo, procedimento de retomada | R06–R08, R14, R39, R41 |
| 03 | A10 | Delegar, consolidar e revisar | 48–51 | divisão útil de trabalho com revisão nas fontes | contratos de papéis, consolidado, revisão | R06, R09–R11 |
| 03 | A11 | Instalar e operar componentes reutilizáveis | 52–55 | componente com ciclo de vida (`source_manifest`) | código, contrato, registro, procedimentos | R32 |
| 03 | A11B | Configurar hooks | 56–59 | hook observável, idempotente e desligável | script, configuração nativa, contrato dos registros | R33 |
| 03 | A11C | Configurar MCP | 60–63 | troca real pelo protocolo + negativa + desligamento | server.py, client.py, traces | R34 |
| 03 | A11D | Criar e compartilhar skills | 64–67 | skill comum e específica descobertas e versionadas | skills, quadro de compatibilidade | R35 |
| 03 | A11E | Instalar e administrar plugins | 68–71 | plugin local com ciclo de vida real | pacote, catálogo, compatibilidade | R36 |
| 04 | A12 | Compartilhar memória persistente autorizada | 72–75 | decisão recuperada em outra sessão/provedor | esquema, operações, pacote de retomada | R16, R18, R19 |
| 04 | A13 | Aplicar isolamento e aprovação de promoção | 76–79 | fronteiras por identidade e promoção por hash | matriz de permissões, procedimento de promoção | R12, R15, R17, R19 |
| 04 | A14 | Corrigir conhecimento e preservar rastreabilidade | 80–83 | correção versionada com conflito e derivados | migrações, procedimento de correção | R04, R18–R20 |
| 05 | A15 | Criar a camada GOLD | 84–88 | conjunto curado explicável item a item | inventário, fichas GOLD, rubrica | R29, R30 |
| 05 | A16 | Ingerir, indexar e recuperar documentos | 89–93 | trechos com página, versão e ID | catálogo, trechos, busca, interface de inspeção | R21, R22, R37 |
| 05 | A17 | Avaliar a recuperação e as respostas | 94–97 | gabarito e métricas separadas | dataset, cálculo, relatório | R22, R23, R25, R42 |
| 05 | A18 | Atualizar, corrigir e remover fontes | 98–101 | ciclo de vida do conhecimento até a restauração | procedimento, grafo, inventário de locais | R20, R24, R31 |
| 06 | A19 | Implementar e demonstrar CAG | 102–106 | reutilização real do estado KV | código, manifesto, evidências do motor | R26, R27 |
| 06 | A20 | Conferir invalidação e isolamento dos caches | 107–110 | velocidade sem ultrapassar acesso | matriz de testes, registros hit/miss/recusa | R24, R28, R31 |
| 06 | A21 | Comparar consumo, tempo e qualidade | 111–114 | otimização decidida por medição | dados brutos, cálculos, decisão | R13, R25, R37–R40 |
| 07 | A22 | Validar o fluxo de petição | 115–118 | pacote de petição rastreável com pendências | caso.json, matriz.md, minuta.md, pendencias.md, revisao.md | — (3.0: R60) |
| 07 | A23 | Migrar e conferir honorários | 119–123 | preço reconstruível com Decimal | entrada.json, calculo.json, demonstrativo, comparacao | R07, R11, R23 |
| 07 | A24 | Migrar e conferir proposta | 124–127 | proposta coerente com o cálculo | proposta.json/.md, comparacao-versoes, validacao | — (3.0: recebe requisito) |
| 07 | A25 | Migrar e conferir contrato | 128–132 | minuta contratual rastreável e bloqueada | contrato.json/.md, rastreabilidade, pendências | R42 |
| 08 | A26 | Criar o segundo projeto e inspecionar o software | 133–138 | reversa-lab sem dados jurídicos + baseline | manifesto, inventario-software, execucao-baseline | — (Ap. B p193: o projeto de software evidencia R02, R04, R09, R18, R41, R42) |
| 08 | A27 | Compreender e documentar | 139–143 | especificação contestável por evidências | SPEC, ARCHITECTURE, EVIDENCE-MAP.csv, UNKNOWN | — (3.0: recebe requisito) |
| 08 | A28 | Criar uma implementação própria | 144–148 | outro programa equivalente no conjunto declarado | código, testes, relatório de compatibilidade | R42 |
| 08 | A29 | Modificar ou modernizar o existente | 149–153 | v1 preservada + v2 com regra nova | pacote, spec v2, antes/depois, retorno | — (3.0: recebe requisito) |
| 08 | A30 | Integrar componentes | 154–158 | CaixaSim 2 integrado à proposta | adaptador, esquemas, mapa de integração | R02, R04, R42, R51 |
| 09 | A31 | Operar a entrada principal por conversa | 159–162 | pedido em linguagem natural → tarefa rastreável | interface, contratos, RELATORIO, RETOMADA | R49, R50 |
| 09 | A32 | Auditar a fundação e os projetos | 163–166 | visão confiável da operação | AUDITORIA, visão de acompanhamento | R41, R43, R50 |
| 10 | A33 | Atualizar com compatibilidade e retorno | 167–169 | atualização planejada com retorno | PLANO-ATUALIZACAO, diff, comparação | R46 |
| 10 | A34 | Habilitar, desabilitar e substituir | 170–173 | ciclo de vida e troca de componente | CICLO-DE-VIDA, registro, adaptadores | R32, R36, R47 |
| 10 | A35 | Restaurar a fundação e retomar | 174–177 | restauração isolada e retomada sem duplicar | RELATORIO-RESTAURACAO, manifesto | R08, R31, R45, R48 |
| 10 | A36 | Demonstrar administração e fechar a matriz | 178–181 | avaliação integrada e matriz reconciliada | RELATORIO-FINAL, matriz, GUIA-DE-OPERACAO | R02, R43, R51 |

| Apêndice | Páginas | Conteúdo | Síntese |
|---|---|---|---|
| A — Glossário | 182–186 | termos operacionais | `references/livro/glossario.md` |
| B — Matriz dos 51 requisitos | 187–193 | R01–R51, estados, regras de revisão | `../requisitos.md`, `assets/templates/MATRIZ-REQUISITOS.csv` |
| C — Prompts para validar, corrigir e retomar | 194–198 | C1–C7 | `../fluxo-c-operar.md` |
| D — Preparar Windows e ambiente | 199–203 | Windows × WSL2, instalação, venv | `references/livro/apendices.md`, `../capacidades/11-manutencao-recuperacao.md` |
| E — Modelos de registros e decisões | 204–209 | mapa de registros, evidências, retomada, decisão, inventário, proveniência, aprovação, aprendizagem | `assets/templates/` |
| F — Verificação editorial e limites | 210–212 | o que foi e o que não foi verificado | `references/livro/apendices.md` |
| Referências verificadas | 213–219 | E01–E44, K01–K19, P01–P11, S01–S19 | `references/livro/apendices.md`, `../fontes-verificadas.md` |

Mapeamento corrigido pela proposta 3.0 (§5.4): R12, R15 e R17 também apontam para a
A12; A01, A02, A22, A24, A26, A27 e A29 ganham requisitos próprios (ex.: A22 → "zero
citações não verificadas", R60).
