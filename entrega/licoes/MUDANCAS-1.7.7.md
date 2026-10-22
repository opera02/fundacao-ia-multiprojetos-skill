# Mudanças da 1.7.7 — efeito e veredito

Versão: 1.7.7 · Anterior: 1.7.6 · Registro: 2026-10-21, antes da liberação. A lista completa está na nota da versão em
`entrega/README-ENTREGA.md`; os achados citados (#1 a #12) são os da auditoria Codex Security sobre a 1.7.6. Efeito
observado nos testes que falhavam antes e passam depois; no host real e em rodadas de avaliação, só onde está dito.
Commits citados são da árvore de desenvolvimento (a cópia pública tem outro histórico).

## Mudanças

| # | Componente | O que mudou | Motivo observado (onde) | Efeito observado (onde) | Veredito |
|---|---|---|---|---|---|
| M1 | `.gitattributes` | o arquivo da cópia pública passa a valer na árvore de desenvolvimento (`* text=auto eol=lf`; commit `4d641a0`) | num clone ou `git archive` no Windows com a configuração padrão do Git, os `.sh` saíam em CRLF e dois testes do preparo do WSL falhavam (revisão de segurança da 1.7.6) | num clone com `core.autocrlf=true`, os `.sh` saíram em LF e os 76 testes do host passaram | ajudou |
| M2 | `fundacao-ia-multiprojetos/scripts/execucao_isolada.py` | o código importado do fluxo B só roda pelo lançador, com plano preso por SHA-256 no aceite do portão 1; bubblewrap no WSL e recusa sem ele, salvo `--sem-isolamento` com motivo (#1) | o portão 1 chamava a execução do B6 de "cópia isolada", mas o programa herdava ambiente, rede e arquivos da conta; um neto destacado gravava depois do prazo | os testes de `fundacao-ia-multiprojetos/scripts/tests/test_auditoria_1_7_6_execucao_isolada.py` que falhavam na 1.7.6 passam; os dois com bubblewrap de verdade passaram no WSL2 e ficam pulados no Windows | ajudou |
| M3 | `fundacao-ia-multiprojetos/assets/fundacao-kit/fundacao/core/ancora_copia.py` | quem restaura é decidido pela fundação viva ou pela cópia autenticada pela âncora; cópia sem âncora só libera com motivo; backup e restauração num preparo privado, preso à identidade dos arquivos (#2 e #12) | a autorização vinha do banco da própria cópia, e uma cópia autoconsistente com o código do kit era liberada só com aviso | os 18 testes novos do kit (`test_auditoria_1_7_7_ancora.py` e `test_auditoria_1_7_7_preparo.py`) falhavam na 1.7.6 e passam; o CEN-09 continua 20/20 | ajudou |
| M4 | `fundacao-ia-multiprojetos/assets/host/preparo_host.py` | o preparo do Windows nunca tira o Python do perfil de destino; o do WSL compara o perfil inteiro com o modelo e fixa o hash do `settings.local.json` e o titular no lançador (#3 e #5) | um `python.exe` indicado num hook do perfil existente era executado; um perfil enfraquecido (rede, credencial, hooks) passava na conferência e era fixado | os testes do host que falhavam passam; no host real, não observado até o titular refazer o preparo nos dois lados | ajudou |
| M5 | `entrega/instalar_skill.py` | a marca da troca interrompida guarda só identificadores, e a recuperação desfaz a troca sem seguir caminho da marca (#4) | a recuperação movia ou apagava caminhos lidos do JSON da marca | os 12 testes de `entrega/testes/test_auditoria_1_7_7_instalacao.py` falhavam e passam (pasta vítima apagada ou promovida antes) | ajudou |
| M6 | `entrega/verificar_pacote.py` | a CI pública confere os pacotes de `entrega/dist` contra a árvore do mesmo commit; o empacotador só roda a ferramenta registrada (#6) | a CI testava a fonte e não o pacote instalável; o empacotador rodava a ferramenta escolhida por quem chama | 16 testes novos; o pacote da 1.7.6 confere com a fonte (190 e 213 arquivos) e a montagem da cópia pública não muda nenhum arquivo da skill | ajudou |
| M7 | `fundacao-ia-multiprojetos/scripts/matriz.py` | matriz e RETOMADA leem só dentro da base; os inventários do B1 e do B3 não atravessam ligação e param nos tetos durante a varredura (#7) | caminho absoluto, `..` e junção eram lidos; o `validar` da RETOMADA chegou a mostrar texto de um arquivo de fora | 17 testes novos; a matriz e a RETOMADA reais da fundação continuam válidas com o código novo (leitura) | ajudou |
| M8 | `fundacao-ia-multiprojetos/scripts/atualizar_fundacao.py` | o `checar` não importa nada da raiz (inventário exato, cópias conferidas, `python -I`); o `desfazer` só aceita registro ancorado; com o kit igual, o `aplicar` regenera o `AGENTS.md` (#8, #10 e o defeito anotado) | um `__init__.py` ou um teste plantado rodava no `checar`; um registro forjado apagava o banco no `desfazer`; o `AGENTS.md` ficou com o texto anterior na 1.7.3 e na 1.7.6 | os testes novos falhavam e passam; a revisão achou e corrigiu também a cadeia de eventos adulterada que nunca bloqueava | ajudou |
| M9 | `fundacao-ia-multiprojetos/assets/fundacao-kit/fundacao/core/publicacao.py` | publicação segura única (temporário imprevisível e exclusivo, sem seguir ligação nem vínculo físico) e teto de saída e de recursos por componente (#9 e #11) | um filho que escrevia 64 MiB levava o pai a 128 MiB; nomes previsíveis seguiam ligação plantada (no Windows, até vínculo físico sem privilégio) | 23 testes novos do kit falhavam e passam; pico medido caiu para 32 MiB com o processo encerrado em 0,2 s | ajudou |
| M10 | `fundacao-ia-multiprojetos/evals/isolamento.py` | gabarito fora do alcance do avaliado, livro-caixa das rodadas, ensaio contrastivo com notas cegas e pass^k nas avaliações de segurança (harness2 P1, P2 e P4; everything-claude-code, proposta 4) | o executor podia ler as expectativas três pastas acima do ambiente e dentro da skill; o verificador lia só `run-1` | não observado: nenhuma rodada real foi feita (tem custo e é decisão do titular); as ferramentas passam nos 28 testes novos | sem efeito observado |
| M11 | `fundacao-ia-multiprojetos/AVISOS-DE-TERCEIROS.md` | avisos de terceiros no pacote, lições com evidência por versão, memória automática do host e modelo de passagem (harness2 P3 e P6; everything-claude-code, propostas 3 e 5) | o modelo de revisão de segurança foi traduzido e adaptado do vibe-coding-toolkit, e o pacote ia sem o aviso MIT dele | o aviso de copyright e o texto MIT passaram a ir no pacote, conferidos por `fundacao-ia-multiprojetos/scripts/tests/test_avisos_de_terceiros.py` | ajudou |
| M12 | `fundacao-ia-multiprojetos/scripts/inventario_plugins.py` | o inventário do host passa a ver o que cada plugin carrega e a acusar matcher defeituoso (everything-claude-code, proposta 1) | hooks de plugins ficavam fora do inventário | neste PC, 9 hooks de plugins antes invisíveis passaram a aparecer, sem alerta de matcher | ajudou |
| M13 | `fundacao-ia-multiprojetos/scripts/tests/test_orcamento_texto.py` | teto que só desce para o texto sempre carregado: corpo e descrição do `SKILL.md` e o `AGENTS.md` gerado (harness2, P5) | o `SKILL.md` cresceu 23,5% da 1.4.5 à 1.7.7 sem nada que pedisse corte | não observado: o teto entrou com os valores atuais | sem efeito observado |
| M14 | `fundacao-ia-multiprojetos/scripts/registro_atualizacao.py` | a revisão de segurança independente da diferença, em três passadas e uma conferência final (a primeira em `f1b7a19..f1bdc88`, cinco revisores por área; a segunda nas variantes do que a primeira corrigiu, R177B; a terceira no que sobrou, R177C, todos de severidade baixa; a conferência final, R177D, achou duas regressões de severidade média nas correções da terceira — a conta "Secretaria" recusada pela matriz e o `verificar` do inventário cego com uma parte malformada — e quatro pontos baixos), achou resíduos nas correções, todos corrigidos antes da liberação: o ensaio do `aplicar` passou a levar `registry/` sem as cópias de código guardadas, o plano do fluxo B a marcar NÃO PRESO o código que vem de fora da cópia sem ser citado, a pasta `mcp/` sem `__init__` a entrar no inventário, entre outros (R177-KIT, R177-FB, R177-VAL, R177-ATU, R177B e R177C) | a simulação da liberação real (skill 1.7.6 instalada, fundação com o kit 1.7.4, pacote 1.7.7) parou no ensaio por uma regressão falsa: um teste achava o seu canário no código antigo guardado pela promoção | a mesma simulação passou depois da correção (355 -> 396 testes, nenhuma regressão), e de novo na terceira passada, nas etapas de pacote, transferência, instalação e atualização da fundação (ensaio com 413 testes, nenhuma regressão); os testes novos de cada resíduo falhavam antes e passam depois | ajudou |

## Lições

### L1 — Promessa de isolamento sem barreira engana o aceite
- Gatilho: um texto que pede aceite (portão, folha de decisões) descreve uma propriedade de segurança, como "cópia
  isolada", que nenhum mecanismo verificável garante.
- Lição: cada promessa de isolamento no texto de aceite aponta o mecanismo e a prova negativa que a sustentam, e o
  aceite fica preso aos parâmetros exatos; sem mecanismo, o texto diz o limite em palavras simples ("roda com toda a
  autoridade da sua conta").
- Evidência: M2; `fundacao-ia-multiprojetos/references/fluxo-b-adaptar.md`;
  `fundacao-ia-multiprojetos/scripts/execucao_isolada.py`
- Confiança: alta

### L2 — Quem confere não executa o que confere
- Gatilho: uma ferramenta de conferência, atualização ou recuperação importa, descobre ou roda código da árvore que
  ainda vai conferir, ou segue caminhos e permissões tirados de um artefato que ainda não autenticou.
- Lição: confira com código confiável e leitura direta, autentique com uma âncora de fora do artefato antes de ler
  dele autorização ou caminhos, e só então rode cópias conferidas; o artefato guarda identificadores, nunca
  caminhos, e o que se abre é conferido como objeto (sem seguir ligação, identidade no lstat e no fstat), não pelo
  nome.
- Evidência: M3, M5, M7, M8, M9; `fundacao-ia-multiprojetos/scripts/codigo_conferido.py`;
  `fundacao-ia-multiprojetos/assets/fundacao-kit/fundacao/core/ancora_copia.py`; `entrega/instalar_skill.py`
- Confiança: alta

### L3 — Ensaie a liberação real antes de liberar
- Gatilho: uma versão muda o kit ou o atualizador, e os testes de unidade usam o mesmo kit com a versão rebaixada ou
  padrões de teste reduzidos.
- Lição: antes de liberar, simule o caminho real inteiro em pastas descartáveis — a skill anterior instalada, uma
  fundação com o kit anterior, o pacote novo, `checar`, `aplicar` e `desfazer` pela skill instalada — e deixe um teste
  com um kit realmente diferente e o padrão de testes padrão; o que só aparece na combinação não aparece nas partes.
- Evidência: M8, M14; `fundacao-ia-multiprojetos/scripts/tests/test_revisao_seguranca_177_atualizador.py`;
  `fundacao-ia-multiprojetos/scripts/codigo_conferido.py`
- Confiança: alta
