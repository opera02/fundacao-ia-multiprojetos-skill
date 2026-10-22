# Mudanças da 1.7.2 — efeito e veredito

Versão: 1.7.2 · Anterior: 1.7.1 · Registro: carga inicial de 2026-10-21.
Só as mudanças que sustentam as lições; a lista completa está na nota da versão em `entrega/README-ENTREGA.md`.
Commits citados são da árvore de desenvolvimento (a cópia pública tem outro histórico).

## Mudanças

| # | Componente | O que mudou | Motivo observado (onde) | Efeito observado (onde) | Veredito |
|---|---|---|---|---|---|
| M1 | `.github/workflows/validar.yml` | os passos da CI depois do primeiro rodam mesmo quando um anterior falhou (`if: ${{ !cancelled() }}` nos quatro últimos) | na primeira CI pública (1.7.1) cada trabalho parou no primeiro passo vermelho e escondeu os demais (commit `dd12133`; nota da 1.7.2) | a CI da 1.7.2 foi a primeira a rodar as verificações até o fim nas dez rodadas e mostrou de uma vez três falhas de ambiente, corrigidas na 1.7.3 (nota da 1.7.3) | ajudou |

## Lições

### L1 — Verificações independentes não param na primeira falha
- Gatilho: uma sequência de verificações independentes numa CI ou num roteiro de liberação.
- Lição: cada verificação independente roda mesmo que uma anterior tenha falhado (no GitHub Actions,
  `if: ${{ !cancelled() }}`), e um teste confere a condição; parar na primeira falha esconde as outras, que só
  aparecem na rodada seguinte.
- Evidência: M1; `.github/workflows/validar.yml`; `entrega/testes/test_ci_publica.py`; `entrega/README-ENTREGA.md`
  (notas da 1.7.2 e da 1.7.3); commit `dd12133`
- Confiança: alta
