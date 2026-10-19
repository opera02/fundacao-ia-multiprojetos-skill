# 02 — Agentes e subagentes: papéis, delegação, paralelismo e revisão

Requisitos: R09, R10, R11. Aula: A10 [Livro p48–51]. Trilha: essencial.

## Objetivo operacional
Dividir trabalho entre executores com responsabilidades distintas e consolidar uma
entrega **atribuída e revisada contra as fontes** — sabendo quando a divisão ajuda e
quando só multiplica mensagens, tempo e consumo.

## Fatos e correções
- Claude Code: subagentes em `.claude/agents/<nome>.md` ou `~/.claude/agents/<nome>.md`;
  `name` e `description` obrigatórios; `tools` opcional (sem ele, herda todas);
  `model` opcional; cada subagente faz suas próprias requisições, que contam nos
  mesmos limites da conta [Verificado 2026-10-18]. Restringir ferramentas no arquivo
  não substitui a autorização de projeto [Livro p49].
- Codex tem subagentes próprios; formatos não são intercambiáveis com os do Claude
  Code [Livro p48] (conferir na versão instalada).
- Custo: sistemas multiagentes podem consumir muitas vezes os tokens de um chat;
  paralelize leitura/amplitude, mantenha cadeias com revisor sequenciais [3.0 R3.4 —
  número citado de fonte secundária, não verificado nesta skill].
- Segundo provedor como verificador independente com rubrica fixa [3.0 R3.5].

## Implementação
1. **Pacote de delegação** por papel: objetivo, arquivos permitidos, papel, limites,
   prazo, orçamento, formato de entrega e **o que fazer quando faltar evidência**
   (registrar ausência, nunca preencher com narrativa plausível) [Livro p48].
2. **Papéis didáticos:** extrator (fatos explícitos + referência) · conferente
   (entradas ausentes + motivo) · consolidador (achados compatíveis, mantendo origem) ·
   revisor (confere o relatório **nas fontes originais**, não só no resumo) [Livro p48].
3. **Paralelismo só entre tarefas independentes**, com fontes somente leitura e
   destinos de saída separados; um único responsável pela consolidação [Livro p49–50].
4. **Contrato distingue** ausência de resultado × resultado vazio válido; participante
   bloqueado deixa lacuna identificada, sem marcar o fluxo integral como concluído [Livro p51].
5. **Divergência resolve-se na evidência**, não por votação nem pelo nome mais
   especializado; rodada de correção limitada [Livro p49–50].
6. Registre `run_id`, papel, provedor, entradas, saídas e vínculo das afirmações às fontes.

## Verificação
| Caso | Esperado |
|---|---|
| Defeitos plantados (afirmação sem fonte; data de emissão usada como data do evento) | revisor encontra ambos, com arquivo, trecho e correção [Livro p49] |
| Paralelismo | horários/eventos de início e fim com sobreposição real (dois arquivos no fim não provam) [Livro p50] |
| Saída incompleta / executor indisponível | consolidado não esconde a falta |
| Fonte de outro projeto | negativa antes da leitura |
| Gabarito do teste | fica fora do contexto do revisor |
| Utilidade | comparação com versão sequencial equivalente (tempo, tentativas, defeitos); sem ganho → fluxo simples [Livro p50] |

## Critério de aceite
Entrega atribuída; defeitos conhecidos detectados; pendências visíveis. A revisão
humana de entrega jurídica é marco próprio e nunca é registrada como feita por agente
[Livro p50].

## Antipadrões
"Squad" no arquivo tratado como coordenação executável; agentes sobrescrevendo o
mesmo arquivo; revisor que repete o texto sem localizar fontes; debate sem limite;
inventar retorno de subagente ausente [Livro p48–51].

## Com o kit
O `Coordinator` executa etapas independentes e consolida por dependências; papéis
são *handlers* com contratos próprios. Exemplo de agente revisor do livro (formato
Claude Code) [Livro p49]: nome `revisor-evidencias`, ferramentas `Read, Glob, Grep`,
instrução de localizar suporte para cada afirmação e indicar ausência, contradição
e troca de significado, sem alterar fontes.
