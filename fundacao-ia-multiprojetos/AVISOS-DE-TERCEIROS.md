# Avisos de terceiros

Origens externas aproveitadas na skill `fundacao-ia-multiprojetos`: projeto, commit analisado, licença e o que foi
aproveitado — **ideia** (método ou regra reescritos com palavras próprias) ou **trecho** (texto traduzido ou
copiado, mesmo que adaptado). Entrada do tipo trecho traz o aviso de copyright e o texto da licença da origem. O
resto da skill é próprio, sob a licença MIT de `LICENSE.txt`. É registro de proveniência, não parecer jurídico.
[Decisão; harness2, P6 — método adaptado de Harness²]

**Critério de citação**, conferido por `scripts/tests/test_avisos_de_terceiros.py`: uma origem é citada quando um
arquivo de texto do pacote instalável (a pasta da skill sem `evals/`) ou as notas de versão da entrega
(`entrega/README-ENTREGA.md`, quando existem) trazem um dos "Nomes no texto" de uma entrada abaixo, ou um rótulo de
origem com nome de repositório: `análise do <projeto>`, `[Decisão; <projeto>, ...]` ou `método adaptado de
<projeto>`, em que `<projeto>` tem letras minúsculas e algarismos, com hífen (como `vibe-coding-toolkit`) ou com
algarismo (como `harness2`). Cada origem citada precisa de uma entrada aqui. Fontes consultadas só para conferir
fatos (documentação oficial, artigos e repositórios de `references/fontes-verificadas.md`) não entram: delas não
veio texto nem código. Cada proposta rotulada no mesmo pacote e nas notas — `<projeto>, [<data>, ]proposta N`,
`<projeto>, P<n>` ou `proposta N da análise do <projeto>` — precisa constar em "Propostas aproveitadas" da entrada
daquele projeto (revisão de segurança da 1.7.7, R177-VAL-10).

## vibe-coding-toolkit

- Projeto: github.com/soumatheusgomes/vibe-coding-toolkit
- Commit analisado: `790a895` (18/10/2026); análise de 21/10/2026, implementada da 1.7.0 à 1.7.3
- Licença: MIT (aviso de copyright e texto abaixo)
- Nomes no texto: vibe-coding-toolkit
- Aproveitamento: trecho
- Trechos, traduzidos e adaptados: `assets/templates/REVISAO-SEGURANCA.md` segue o modelo de revisão de segurança do
  toolkit — a ordem das seções, os campos de escopo, cobertura, achado e pendências e o parágrafo final de limites;
  `assets/templates/AUDITORIA-SEGURANCA.md` reaproveita, em versão enxuta, a ordem das seções, os campos de
  achado e de pendências e a frase final de limites.
  Frases de regras, mais curtas, estão na regra de ondas de `references/capacidades/02-agentes-subagentes.md`, nas
  regras de continuidade de `assets/templates/AGENTS-RAIZ.md`, na reavaliação do comportamento do C10 em
  `references/fluxo-c-operar.md` e na nota de achados de `assets/templates/AUDITORIA.md`.
- Ideias, sem trecho: as demais propostas da análise, rotuladas "análise do vibe-coding-toolkit" nas referências e
  no código (instruções da raiz, pastas de dados fora das instruções, política de rotas validada, catraca de testes,
  CI pública, RETOMADA enxuta, comandos citados conferidos, canários, fronteiras do código, órfãos do kit, avaliações
  E10 a E12 e inventário do host). O código da skill é Python próprio; o do toolkit é JavaScript.
- Propostas aproveitadas: 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14 e 15 (numeração da análise; o que cada uma
  trouxe está nas duas linhas anteriores e no rótulo "proposta N" de cada arquivo)

Aviso de copyright e licença, como estão no arquivo LICENSE do toolkit no commit analisado:

```text
MIT License

Copyright (c) 2026 Matheus Gomes

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## harness2

- Projeto: github.com/google-research/harness2 — Harness²: Recursive Agent Harnessing for an Open World (Xu e
  outros, 2026, arXiv:2610.14224)
- Commit analisado: `1cfe254` (13/10/2026); análise de 21/10/2026, implementada na 1.7.7
- Licença: Apache-2.0 (o projeto não tem arquivo NOTICE)
- Nomes no texto: harness2, Harness²
- Aproveitamento: ideia
- O que foi aproveitado: o método, escrito com palavras próprias — mudança, efeito e veredito, e lição com
  evidência (§5 e §5b de `assets/templates/RELATORIO-FINAL.md`, a linha "Lição" de `assets/templates/EVIDENCIAS.md`,
  §Lições de `references/capacidades/04-memoria.md` e, na árvore de desenvolvimento, `entrega/licoes.py`) e este
  registro de proveniência. Outras propostas da mesma análise que entrarem na versão também vêm só como ideia.
  Nenhum texto ou código copiado; nada de `third_party/` nem de dados de benchmark. Se um trecho entrar, vão para o
  pacote o texto da Apache-2.0, o aviso de modificação no arquivo e os avisos de autoria do original.
- Propostas aproveitadas: P1 (livro-caixa das rodadas de avaliação), P2 (gabarito fora do alcance do avaliado), P3
  (mudança, efeito e veredito; lição com evidência), P4 (ensaio contrastivo com notas cegas), P5 (teto que só desce
  para o texto sempre carregado) e P6 (este registro de proveniência)
- Atribuição: método adaptado de Harness² (arXiv:2610.14224, github.com/google-research/harness2, commit 1cfe254,
  Apache-2.0).

## everything-claude-code

- Projeto: github.com/WorldFlowAI/everything-claude-code, fork de github.com/affaan-m/everything-claude-code
- Commit analisado: `432485b` (23/01/2026); análise de 21/10/2026, implementada na 1.7.7
- Licença: não confirmada — o README e o manifesto do plugin declaram MIT, mas o fork não tem arquivo de licença;
  por isso nada foi copiado
- Nomes no texto: everything-claude-code
- Aproveitamento: ideia
- O que foi aproveitado: ideias reescritas com palavras próprias — o inventário dos plugins do host por dentro, com
  os alertas de matcher e de evento (`scripts/inventario_plugins.py`, `scripts/alertas_hooks.py` e §1 de
  `references/capacidades/08-ferramentas-hooks-mcp-skills-plugins.md`), a regra para a memória automática do host
  (§Memória automática do host de `references/capacidades/04-memoria.md` e a linha de
  `assets/templates/AGENTS-RAIZ.md`), as avaliações repetidas, em que a de segurança só passa se passar em todas as
  execuções (C10 de `references/fluxo-c-operar.md`, §5 de `references/principios-e-evidencias.md` e, na árvore de
  desenvolvimento, `evals/`) e a passagem do trabalho delegado (`assets/templates/PASSAGEM.md` e o pacote de
  delegação de `references/capacidades/02-agentes-subagentes.md`).
- Propostas aproveitadas: 1 (inventário dos plugins do host: hooks, MCP e skills de cada plugin), 3 (memória
  automática do host), 4 (avaliações repetidas: pass@k e pass^k) e 5 (passagem do trabalho delegado)
