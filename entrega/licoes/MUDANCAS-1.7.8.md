# Mudanças da 1.7.8 — efeito e veredito

Versão: 1.7.8 · Anterior: 1.7.7 · Registro: 2026-10-22, antes da liberação.
O mesmo conteúdo da 1.7.7, com as três falhas da CI pública dela corrigidas; a lista completa está na nota da versão
em `entrega/README-ENTREGA.md`. Commits citados são da árvore de desenvolvimento (a cópia pública tem outro histórico).

## Mudanças

| # | Componente | O que mudou | Motivo observado (onde) | Efeito observado (onde) | Veredito |
|---|---|---|---|---|---|
| M1 | `fundacao-ia-multiprojetos/references/comunicacao-leigo.md` | o texto, e o docstring de `fundacao-ia-multiprojetos/scripts/tests/test_revisao_seguranca_177c_atualizador.py`, não citam mais a raiz real com a letra da unidade (commit `81b232a`); na ferramenta privada de liberação, a pré-checagem passou a recusar o saneamento que mudaria arquivo do pacote, e as etapas 02 e 03 varrem o texto de dentro dos zips | a CI pública da 1.7.7 reprovou "pacotes versionados iguais à fonte" nos 10 jobs: o saneamento da cópia pública trocou o caminho por um marcador, e a cópia publicada ficou diferente do pacote (nota da versão em `entrega/README-ENTREGA.md`) | a montagem saneada a partir de `81b232a` não muda nenhum arquivo do pacote nem o instalador; a pré-checagem nova acusava os dois arquivos na 1.7.7 e passa na 1.7.8 | ajudou |
| M2 | `fundacao-ia-multiprojetos/scripts/tests/test_orcamento_texto.py` | a medida do `AGENTS.md` troca por `<raiz>` todas as formas do caminho da raiz, a dada e a resolvida | na CI do Windows, os 5 jobs reprovaram dois testes: a pasta temporária vem pelo nome curto 8.3, e o `AGENTS.md` cita o caminho resolvido | com a pasta temporária atrás de uma junção (o mesmo descompasso), a versão anterior falha nos mesmos dois testes e a corrigida passa; a revisão conferiu que um caractere a mais no modelo ainda reprova | ajudou |
| M3 | `entrega/testes/test_revisao_1_7_7_terceira_passada_avaliacoes.py` | o caso do prefixo de dispositivo do Windows no rastro das avaliações roda só no Windows, com o motivo; o caso sem prefixo roda em todo sistema | na CI do Ubuntu, os 5 jobs reprovaram o caso do próprio ambiente com o prefixo, que no Linux não designa lugar | no Ubuntu do WSL (Python 3.12.3), em `81b232a`, a suíte da entrega passou com o caso pulado (255 testes, 8 pulados), e o kit (418) e os scripts (445) também passaram | ajudou |
| M4 | `fundacao-ia-multiprojetos/SKILL.md` | versão 1.7.8, com o kit igual (1.7.7) | o pacote da 1.7.7 ficou na lista dos liberados, que só cresce, e o número não se reutiliza (como a 1.6.0 e a 1.7.4) | não observado: registro feito antes da liberação | sem efeito observado |

## Lições

### L1 — O saneamento da cópia pública não pode mudar arquivo do pacote
- Gatilho: um texto da skill cita caminho ou nome que o saneamento da cópia pública troca por um marcador, ou um zip
  publicado leva texto com dado local (o saneamento não abre zip).
- Lição: antes de publicar, monte a cópia saneada e recuse se ela mudar arquivo do pacote ou da transferência, e
  varra o texto de dentro dos zips com as mesmas regras; exemplos na skill usam marcador (`<raiz>`), nunca o caminho
  real.
- Evidência: M1; `fundacao-ia-multiprojetos/references/comunicacao-leigo.md`; `entrega/README-ENTREGA.md`; commit
  `81b232a`
- Confiança: alta

### L2 — A CI pública roda em outro sistema e em outro caminho
- Gatilho: teste novo que depende do sistema operacional ou da forma do caminho temporário.
- Lição: antes de liberar, rode as suítes também no Linux (WSL) e com a pasta temporária atrás de um nome que não é
  o resolvido (junção), como a CI; o que só existe no Windows fica marcado e pulado fora dele, com o motivo.
- Evidência: M2, M3; `fundacao-ia-multiprojetos/scripts/tests/test_orcamento_texto.py`;
  `entrega/testes/test_revisao_1_7_7_terceira_passada_avaliacoes.py`
- Confiança: alta
