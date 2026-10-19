# Skill Benchmark: fundacao-ia-multiprojetos

**Model**: claude-opus-5-5 (subagentes general-purpose)
**Date**: 2026-10-18T23:33:00Z
**Evals**: 1, 2, 3, 4, 5, 6, 7, 8 (1 runs each per configuration)

## Summary

| Metric | With Skill | Without Skill | Delta |
|--------|------------|---------------|-------|
| Pass Rate | 100% ± 0% | 94% ± 8% | +0.06 |
| Time | 3163.0s ± 1435.1s | 2536.1s ± 1638.4s | +626.9s |
| Tokens | 301727 ± 142533 | 238841 ± 188203 | +62887 |

## Notes

- Aprovação: com skill 46/46 (100%); sem skill 39/42 (92,9%) em E1–E7; E8 só tem configuração com skill (4/4). O delta é pequeno porque a maioria das asserções não discrimina — os avaliadores apontaram isso em E3, E4, E5 e E7.
- Linha de base favorecida: em E2–E7 o kit de referência (parte da skill) já estava instalado no ambiente das duas configurações, porque o cenário pressupõe fundação existente. O delta mede o valor do SKILL.md + referências sobre o kit, não o valor total da skill.
- Reprovações sem skill: E1 #3 (a CLI criada pela linha de base lia o outro projeto sem identidade quando rodada da raiz; negativa só no sentido oposto e sem registro útil); E2 #1 (diagnóstico escrito só depois da primeira alteração); E6 #6 (sem registro de retomada).
- Diferenças reais fora das asserções (observadas pelos avaliadores): com skill houve backup verificado antes de alterar, RETOMADA validada, matriz de requisitos e evidências por etapa; em E7 a linha de base leu arquivos do outro projeto com cat antes de conferir a autorização; em E5 a linha de base gravou código e testes novos na fundação sem referência recuperável prévia.
- Custo: com skill, em média +627 s e +63 mil tokens por execução (mais verificações, ensaios em cópia, backups e registros).
- Executores das duas configurações acharam 11 defeitos reais no kit 1.0.0 (estado da tarefa; backup/eventos sem identidade; saídas com caminho absoluto; UTF-8 em componentes; rota sigilosa escoando para API paga; ambiente mínimo sem USERNAME; vazamentos de metadados F01–F03 e O1–O3). Todos corrigidos no kit 1.1.0 e cobertos por testes (76 OK).
- Uma execução por configuração: os ± refletem variação entre avaliações, não repetibilidade. Desvio de protocolo: subagentes gravaram scripts temporários no scratchpad da sessão (instrução do host); arquivos em evals/ foram editados pelo orquestrador durante as execuções, sem relação com as tarefas.