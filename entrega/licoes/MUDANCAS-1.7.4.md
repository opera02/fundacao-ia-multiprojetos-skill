# Mudanças da 1.7.4 — efeito e veredito

Versão: 1.7.4 · Anterior: 1.7.3 · Registro: carga inicial de 2026-10-21 (a 1.7.4 ficou só empacotada; a 1.7.5 é
ela com um arquivo em LF). Só as mudanças que sustentam as lições; a lista completa está na nota da versão em
`entrega/README-ENTREGA.md`. Commits citados são da árvore de desenvolvimento (a cópia pública tem outro histórico).

## Mudanças

| # | Componente | O que mudou | Motivo observado (onde) | Efeito observado (onde) | Veredito |
|---|---|---|---|---|---|
| M1 | `fundacao-ia-multiprojetos/assets/fundacao-kit/fundacao/core/decisoes.py` | as decisões do titular passam a valer na ordem da data de preparo, que está no conteúdo assinado, e não na do registro (E11 F-02; commit `d5645cf`) | valia a última decisão registrada: um aceite antigo registrado depois de uma rejeição concluía a tarefa (sonda A da avaliação E11; nota da 1.7.4) | a sonda A passou a ser recusada; a revisão de segurança da versão achou datas escolhidas por quem prepara que ainda invertiam a ordem (E11R-04; nota da 1.7.4) | ajudou |
| M2 | `fundacao-ia-multiprojetos/assets/fundacao-kit/fundacao/core/decisoes.py` | cada decisão cita, no conteúdo assinado, a vigente da tarefa (`anterior_sha256`), conferida e gravada na mesma transação (E11R-04 e E11R-05; commit `97d32e7`) | a data de preparo é escrita por quem prepara: datas para trás, para a frente ou empatadas invertiam a ordem, e conferir e gravar ficavam em transações separadas (sondas E a H da revisão) | as sondas A e E a H passaram a ser recusadas (`fundacao-ia-multiprojetos/assets/fundacao-kit/tests/test_avaliacao_e11_ordem_decisoes.py`); a passada seguinte da revisão achou um aceite assinado de antemão, encadeado numa rejeição ainda não registrada (E11R-06) | ajudou |
| M3 | `fundacao-ia-multiprojetos/assets/fundacao-kit/fundacao/core/decisoes.py` | a decisão cita também o hash do evento que registrou a vigente (`anterior_evento`), que ninguém prevê antes do registro (E11R-06; commit `d71ff85`) | sonda I3 da revisão: o aceite assinado de antemão entrava logo depois do registro da rejeição em que foi encadeado | a sonda I3 passou a ser recusada; a revisão consolidada da 1.7.5 não achou nada novo (commit `fcf2f20`) | ajudou |
| M4 | `entrega/avaliacoes/AVALIACOES.md` | o modelo da iteração 3 corrigido para o que o rastro das três execuções registra (commit `6083d2f`) | a primeira partida da nova execução da E10 foi interrompida depois de 8 chamadas, sem nota: o coordenador confundiu o modelo dela com o da iteração 3, que o registro dava errado até a 1.7.3 | a execução avaliada, a segunda partida, usou o mesmo modelo da iteração 3, conferido no rastro (iteração 4 em `entrega/avaliacoes/AVALIACOES.md`) | ajudou |

## Lições

### L1 — Ordem que quem prepara escolhe não é ordem
- Gatilho: a vigência ou a ordem de registros (decisões, aprovações, eventos) depende de um valor que quem prepara o
  registro escreve, como data, número de sequência ou referência à anterior.
- Lição: amarre a ordem a valores que quem prepara não escolhe nem prevê (o hash da vigente e o do evento que a
  registrou, dentro do conteúdo assinado), confira e grave na mesma transação e peça à revisão que tente escolher
  esses valores.
- Evidência: M1, M2, M3; `entrega/README-ENTREGA.md` (nota da 1.7.4);
  `fundacao-ia-multiprojetos/assets/fundacao-kit/tests/test_avaliacao_e11_ordem_decisoes.py`; commits `d5645cf`,
  `97d32e7` e `d71ff85`
- Confiança: alta

### L2 — O modelo de uma execução sai do rastro dela
- Gatilho: registrar, comparar ou repetir uma execução de avaliação (modelo, executor, versão da skill).
- Lição: leia o modelo de cada execução no rastro dela e grave-o junto com a nota; antes de uma nova partida,
  confira o registro contra o rastro, porque o que se lembra do modelo pode estar errado.
- Evidência: M4; `entrega/avaliacoes/AVALIACOES.md` (iterações 3 e 4); commit `6083d2f`
- Confiança: média
