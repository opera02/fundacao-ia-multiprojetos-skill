# Mudanças da 1.7.1 — efeito e veredito

Versão: 1.7.1 · Anterior: 1.7.0 (empacotada e recusada na transferência) · Registro: carga inicial de 2026-10-21.
Só as mudanças que sustentam as lições; a lista completa está na nota da versão em `entrega/README-ENTREGA.md`.
Commits citados são da árvore de desenvolvimento (a cópia pública tem outro histórico).

## Mudanças

| # | Componente | O que mudou | Motivo observado (onde) | Efeito observado (onde) | Veredito |
|---|---|---|---|---|---|
| M1 | `fundacao-ia-multiprojetos/scripts/tests/test_inventariar_host.py` | a variável fictícia do exemplo de configuração do Codex trocou de nome | a montagem da transferência da 1.7.0 leu o valor fictício como token atribuído e recusou o pacote (commit `7e5d5c4`; nota da 1.7.1) | a transferência da 1.7.1 foi montada (`entrega/transferencia/fundacao-ia-multiprojetos-1.7.1-para-revisao.md`) | ajudou |
| M2 | `fundacao-ia-multiprojetos/scripts/tests/test_pacote_sem_segredo_aparente.py` | teste novo: os padrões da varredura da transferência valem para todo o pacote (a skill sem `evals/`) | o falso positivo da 1.7.0 era da mesma classe do que parou a 1.6.0, e a regressão criada na 1.6.1 cobria só o preparo do host (notas da 1.6.1 e da 1.7.1) | nenhuma liberação seguinte parou na varredura (transferências da 1.7.2, 1.7.3, 1.7.5 e 1.7.6 montadas), mas não há registro de o teste ter pego um caso | confundido |

## Lições

### L1 — Regressão de uma varredura cobre tudo o que a varredura lê
- Gatilho: uma verificação automática da liberação (varredura de segredos, saneamento, lista de padrões) recusa o
  pacote por causa de um arquivo.
- Lição: além de corrigir o arquivo, aplique os mesmos padrões, num teste, a tudo o que a verificação vai ler, antes
  de empacotar; a regressão feita só para o arquivo do incidente deixa a mesma classe voltar noutro arquivo.
- Evidência: M1, M2; `entrega/README-ENTREGA.md` (notas da 1.6.1 e da 1.7.1);
  `fundacao-ia-multiprojetos/scripts/tests/test_pacote_sem_segredo_aparente.py`; commits `2ce74a3` e `7e5d5c4`
- Confiança: média
