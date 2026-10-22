# Mudanças da 1.7.6 — efeito e veredito

Versão: 1.7.6 · Anterior: 1.7.5 · Registro: carga inicial de 2026-10-21.
A mudança principal da versão e a que sustenta a lição; a lista completa está na nota da versão em
`entrega/README-ENTREGA.md`. Commits citados são da árvore de desenvolvimento (a cópia pública tem outro histórico).

## Mudanças

| # | Componente | O que mudou | Motivo observado (onde) | Efeito observado (onde) | Veredito |
|---|---|---|---|---|---|
| M1 | `fundacao-ia-multiprojetos/references/fluxo-b-adaptar.md` | B7 a B9: a ferramenta que roda os casos do golden pela fundação fica no projeto, conferida por manifesto, e roda com `python -P` | na nova execução da E10, a comparação usou um script temporário da sessão e a RETOMADA citou outro arquivo (iteração 4 em `entrega/avaliacoes/AVALIACOES.md`) | não observado: a regra foi escrita sem nova execução da E10; o cenário do fluxo B (CEN-02 e CEN-03) passou a segui-la | sem efeito observado |
| M2 | `fundacao-ia-multiprojetos/SKILL.md` | liberação só da skill (versão 1.7.6), com o kit igual (1.7.4) | a regra do M1 pedia versão nova da skill; o kit não mudou | na fundação, a atualização terminou em "nada a fazer" e o `AGENTS.md` da raiz ficou com a versão anterior até ser regenerado à mão, como já tinha acontecido na 1.7.3 (relatos de implementação no projeto, fora da árvore) | piorou |

## Lições

### L1 — O que deriva da versão da skill acompanha a versão
- Gatilho: uma versão muda só a skill (texto ou scripts), e o kit e o resto da fundação ficam iguais.
- Lição: tudo o que é gerado a partir da versão da skill, como o `AGENTS.md` da raiz, é regenerado e conferido
  (`instrucoes_raiz.py conferir`) na atualização da fundação; o "nada a fazer" do kit não cobre a skill. Deixar a
  correção anotada "para a versão seguinte", sem lugar fixo, fez o defeito voltar.
- Evidência: M2; `fundacao-ia-multiprojetos/scripts/instrucoes_raiz.py`;
  `fundacao-ia-multiprojetos/scripts/atualizar_fundacao.py`; `entrega/README-ENTREGA.md` (nota da 1.7.7, com os
  dois defeitos anotados na 1.7.6); commit `c74a42f`
- Confiança: alta
