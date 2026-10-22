# 10 — Observabilidade e operação por conversa

Requisitos: R41, R42, R43, R49, R50, R51 (e R57 da 3.0). Aulas: A31 [Livro
p159–162], A32 [Livro p163–166]; 3.0 §3.10. Trilha: essencial (auditoria) ·
avançada (interface de conversa) [3.0 §5.1].

## Entrada principal por conversa (R49, R50) [Livro A31]
Conversar não é executar imediatamente: resolva referências pelo contexto
**autorizado** e pergunte só quando a ambiguidade muda o trabalho ("o contrato da
proposta v2 ou o rascunho v1?").

1. Obtenha a identidade da sessão confiável e **liste só os projetos permitidos**.
2. Fixe projeto e versões de entrada **na criação da tarefa**; trocar de projeto na
   tela não muda o escopo de uma tarefa em andamento (estado de navegação ≠ escopo
   imutável da execução) [Livro p162].
3. Operações pequenas: iniciar tarefa · consultar estado · listar artefatos do projeto
   · retomar `run_id`. Entradas por identificador e versão, nunca caminho livre do modelo.
4. Contrato conversa→execução (didático): `request_id`, `project_id`, `operation`,
   `input_artifacts[{id, revision}]`, `expected_output`, `resume_run_id`; a identidade
   **não** está no pedido [Livro p160]. Modelo: `assets/templates/CONTRATO.schema.json`.
5. Estados visíveis: recebido · em execução · aguardando revisão · falhou · cancelado ·
   concluído — sempre o estado **persistido**; "concluído" exige artefato validado
   [Livro p160–161].
6. Histórico da conversa ajuda a interpretar "a revisão anterior"; memória de projeto
   guarda decisões aprovadas; frase casual não vira memória comum sem o fluxo de
   promoção [Livro p160].
7. Transparência útil = fontes, operações, resultados, critérios e limites — não exibir
   raciocínio interno do modelo [Livro p161].
Provas: pedido normal; reenvio do mesmo pedido (sem duplicar); interrupção e retomada
após reinício; troca de projeto com tarefa ativa; referência inexistente; leitura de
outro projeto; documento com instrução maliciosa [Livro p161].
Teste do usuário: sem abrir código, ele responde "em que projeto estou, o que foi
pedido, qual o estado real, que decisão falta" [Livro p161].

## Logs, métricas e rastros (R41, R43, R57) [Livro A32; 3.0 R10]
Log = evento; métrica = quantidade agregada; rastro = etapas de uma solicitação
[Livro p163]. Comece com SQLite + JSONL; OpenTelemetry (atributos `gen_ai.*`) é opcional
e não exige enviar documentos/prompts a serviço externo.
Esquema de evento: `ts` UTC, `schema_version`, `trace_id`/`run_id`, `task_id`,
`project_id`, `principal`, componente, tipo, artefato, duração, tokens (`null` = não
medido), estado de custo [Livro p163; 3.0 R10.1]. Eventos com finalidade: criação,
transição, chamada, negativa, erro, resultado, aprovação [Livro p165].
Trilha à prova de edição: `prev_hash` encadeado; pasta fora do alcance de escrita do
agente; ancoragem periódica (commit assinado/carimbo) [3.0 R10.3]. Kit:
`fundacao/core/events.py` (`emit` na mesma transação, `verify_chain`, `export_jsonl` — que acrescenta por
`publicacao.anexar`: destino que é ligação ou vínculo físico recusa sem gravar nem marcar eventos; revisão de
segurança da 1.7.7, R177-KIT-04).

## Painel que ajuda a decidir (R50) [Livro p163–164]
Cinco blocos: tarefas por estado · falhas recentes · requisitos sem evidência · consumo
por modalidade · qualidade por cenário; filtros por projeto/período sujeitos à
autorização. Evite: ignorar tarefas abandonadas (denominador incompleto), mostrar só o
melhor tempo (use mediana e cauda), usar tamanho de resposta como qualidade, tratar
ausente como zero. Média global esconde projeto que falha. Painel é representação dos
registros, não prova independente [Livro p163]. [3.0 R10.4] Datasette sobre cópia
somente leitura; Langfuse/Phoenix na trilha avançada.

## Auditoria (R42, R43)
Siga o procedimento C10 de `references/fluxo-c-operar.md` e o modelo
`assets/templates/AUDITORIA.md`. Inclua sempre exemplos de controle com erro conhecido
(o "revisor que sempre aprova" não mede nada) [Livro p165].

## Administração pelo usuário (R51) [Livro A36 p178–181]
Avaliação em duas partes: funcionamento da fundação × administração pelo usuário
(formular objetivo com limites e critério, conferir evidência, pedir correção, explicar
aceite/rejeição, criar outro projeto). [Decisão — adaptação pedagógica] O "registro de
aprendizagem" do livro vira **registro de decisões e entendimento do usuário**:
descreve o que o usuário efetivamente demonstrou numa interação real (ex.: identificou
uma citação sem suporte, escolheu o escopo de um dado), nunca o que se presume.
