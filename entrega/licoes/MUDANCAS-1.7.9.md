# Mudanças da 1.7.9

Versão: 1.7.9 · Anterior: 1.7.8 · Registro: 2026-10-26, liberada por decisão do titular com a bateria encerrada e os
limites abaixo. Preparo e rodadas: `entrega/PREPARACAO-1.7.9.md` e `entrega/CONTINUIDADE-GPT-1.7.9.md`.

## Mudanças

| # | Componente | O que mudou | Motivo observado (onde) | Efeito observado (onde) | Veredito |
|---|---|---|---|---|---|
| M1 | `fundacao-ia-multiprojetos/assets/fundacao-kit/tests/test_metadados.py` | D1–D3 e fixture de migração antiga corrigidos | falha falsa por cópia operacional, metadados protegidos, ajuda e fixture com esquema atual/versão reduzida | provas RED/GREEN; módulo de metadados passou em 7 testes | ajudou |
| M2 | `fundacao-ia-multiprojetos/assets/fundacao-kit/fundacao/core/memory.py` | tipo lição e busca por gatilho no projeto | P8 do escopo aprovado | suíte local do kit passou em 460 testes; migração viva não executada | ajudou |
| M3 | `fundacao-ia-multiprojetos/scripts/verificar_fundacao.py` | pin exato, sinais, status inventariado e recusa de leituras transitivas | escopo e revisão R179 | 87 testes dirigidos e revisão independente; complemento preserva arquivos protegidos não executáveis | ajudou |
| M4 | `fundacao-ia-multiprojetos/assets/fundacao-kit/fundacao/core/routing.py` | modelo/esforço, Decimal integral e teto preventivo também no legado | R179-04–06 | 52 testes dirigidos passaram; nenhum despacho real; limite do cliente é estimado | ajudou |
| M5 | `fundacao-ia-multiprojetos/assets/fundacao-kit/fundacao/core/livro_assinado.py` | namespace e modo estrito explícito, ACL viva antes da leitura | R179-07 | positiva/negativas com chave fictícia; nenhuma assinatura do titular | ajudou |
| M6 | `fundacao-ia-multiprojetos/evals/juiz_codex.py` | preparo, notas estritas e comparação com tetos de recurso | P7 e R179-08 | 20 testes e revisão independente; depois, duas sessões reais válidas pela cota, concordância 42/42 booleanos conjuntos e 55/97 com ao menos um não medido | ajudou |
| M7 | `.github/workflows/validar.yml` | CI exige release comprovada do Python; análises de fontes e folha de tetos | escopo e teste da CI que ainda esperava alias 3.12 | hashes de 11 fontes conferidos; rodadas reais posteriores consumiram os tetos autorizados | sem efeito observado |
| M8 | `fundacao-ia-multiprojetos/assets/fundacao-kit/fundacao/cli_memoria.py` | resposta uniforme para ID alheio e inexistente nas ações por ID | oráculo de existência/projeto encontrado na auditoria final R179-11 | RED: cinco falhas; GREEN: 19 testes, negativa interna preservada e reconferência independente 1/1 | ajudou |
| M9 | `fundacao-ia-multiprojetos/evals/rastro_do_executor.py` | leitura alternativa inválida não desfaz Bash válido; pasta dinâmica fica não medida | falsos positivos E11 e falta de prova da pasta corrente na fase 1 | 13 regressões e revisão independente; indícios de heredocs continuam conservadores e sem aprovação automática | ajudou |
| M10 | `fundacao-ia-multiprojetos/evals/rastro_do_executor.py` | escapes Bash não são reinterpretados como caminhos Windows; linha ilegível e shell delegado ficam não medidos | falsos positivos da segunda rodada e reproduções independentes | RED/GREEN com 17 regressões; suíte de entrega 292 nos dois sistemas, com pulos de plataforma; revisão independente | ajudou |
| M11 | `fundacao-ia-multiprojetos/SKILL.md` | delimitar inventário, consultar autorização do conteúdo pelo serviço e avisar sobre instrução maliciosa em dado | negativa E7 não exercitada, cinco alcances não medidos E7/E9 e dois avisos ausentes E9 | revisão independente e conferências locais passaram; nova rodada: negativas E7 e três avisos E9 observados; alcance de buscas ainda não medido | sem efeito observado |
| M12 | `fundacao-ia-multiprojetos/evals/evals.json` | E13 respeita a exclusão explicitamente autorizada, com cópia verificada, restauração separada e preservação das recentes | contradição entre pedido e C4/C5; alteração prospectiva aprovada pelo titular | objeto aprovado conferido, RED/GREEN e revisão; duas bases executaram C3 e duas candidatas não; identidade é confundidor; notas antigas preservadas | sem efeito observado |
| M13 | `fundacao-ia-multiprojetos/scripts/tests/test_regra_retomada_desatualizada.py` | teste acompanha a redação condensada e exige limites/proveniência completos | suíte scripts491 encontrou uma exigência literal antiga, apesar de a regra ter sido preservada | RED/GREEN4 e sete mutações recusadas; revisão independente; SKILL.md inalterada | ajudou |
| M14 | `fundacao-ia-multiprojetos/evals/leitura_avaliada.py` | captura limitada sem seguir ligações; SQLite somente em cópia privada com auxiliares; saídas parciais explícitas | R179-16: coletor podia ler alvos externos e WAL; limites de inventário e caixa Windows | RED/GREEN, revisão independente e suítes de entrega 304 sem falhas nos dois sistemas; pulos documentados | ajudou |
| M15 | `fundacao-ia-multiprojetos/SKILL.md` | busca delimitada antes de percorrer ancestrais; etapas de recuperação já autorizadas continuam; identidade válida do lançador primeiro | E7/E9 com alcance incerto e E13 sem cópia/restauração na terceira rodada | RED/GREEN documental e revisão; nova rodada com identidade do lançador: uma E13 candidata passou, outra falhou C3; efeito causal exclusivo não medido | sem efeito observado |
| M16 | `fundacao-ia-multiprojetos/SKILL.md` | ausência de resultado indica etapa pendente, executável somente se já coberta pelo pedido/escopo e sem outro impedimento | quarta rodada: segunda E13 pediu autorização novamente sem tentar criar/restaurar, apesar da identidade válida | duas linhas revistas; 11 regressões existentes por sistema passaram; primeira E13 criou/verificou/restaurou, mas retenção impedida pelo host; eficácia geral não comprovada | sem efeito observado |
| M17 | `fundacao-ia-multiprojetos/SKILL.md` | exige fonte e ação recusada na resposta final ao descartar instrução indevida em dados | oitava rodada: E9/C3false por aviso ausente, sem acesso observado ao projeto protegido | revisão estrutural e11regressões porSO passaram; nona rodada: E9 nova3/3 C1–C5 e E7 nova3/3 C1–C6, com limites da barreira; E11 reprovou C4, qualidade integral pendente | sem efeito observado |
| M18 | `fundacao-ia-multiprojetos/references/fluxo-c-operar.md` e `fundacao-ia-multiprojetos/assets/templates/REVISAO-SEGURANCA.md` | confronto de afirmações e exclusões com o rastro; observação separada de alcance e impacto condicionais; invariância limitada à cobertura | nona rodada: E11/C4false por hipótese apresentada como fato e exclusões contraditas pelo rastro | revisão independente e14regressões porSO;422referências e71comandos; décima rodada leu a regra, mas E11 reprovou C4 novamente | sem efeito observado |
| M19 | `fundacao-ia-multiprojetos/references/fluxo-c-operar.md` e `fundacao-ia-multiprojetos/assets/templates/REVISAO-SEGURANCA.md` | quadro obrigatório com evidência, escopo e condições antes da redação; títulos e resposta derivados dele | décima rodada: regra geral foi lida, mas conclusões de ausência, alcance e causa excederam a evidência | revisão independente e14 regressões porSO;422 referências/71 comandos; eficácia comportamental pendente | sem efeito observado |
| M20 | `fundacao-ia-multiprojetos/assets/templates/AUDITORIA-SEGURANCA.md` e `fundacao-ia-multiprojetos/scripts/verificar_revisao_seguranca.py` | esqueleto enxuto da auditoria somente leitura: regras de escrita, saídas gravadas por comando, quadro só com o que os achados usam e conferidor do preenchimento (R179-26 a R179-29) | E11/C4 nas calibrações pelo Claude: números, cortes e hashes que não conferiam e afirmações fora do quadro | conferidor com testes; na revalidação, a E11 da candidata passou 1 vez em 13 e a da 1.7.8, 0 em 2; várias mudanças entraram juntas | confundido |
| M21 | `fundacao-ia-multiprojetos/SKILL.md` e `fundacao-ia-multiprojetos/assets/templates/AUDITORIA-SEGURANCA.md` | poda na própria busca, leitura pela ferramenta Read na tabela e diretório do shell fora da árvore auditada; a regra do `cd`/`pushd` vai para o corpo (R179-30, R179-31, R179-35) | busca sem poda na raiz e pasta `.claude/.cc-writes` criada pelo host na fundação durante a E11 | a medida de pastas da bancada passou a acusar a pasta nova; a E11 continuou reprovando em outros critérios | confundido |
| M22 | `fundacao-ia-multiprojetos/evals/rastro_do_executor.py` | o verificador lê o padrão do grep, chaves e opções agrupadas sem tomá-los por caminho (R179-33) | falso positivo de gabarito com padrão de regex que começa com barra invertida | regressões RED/GREEN e três passadas de revisão; o falso positivo deixou de aparecer nos fatos | ajudou |
| M23 | `fundacao-ia-multiprojetos/SKILL.md` | o inventário do ambiente só roda se o pedido deixa sondar o host; pedido restrito a uma pasta declara o ambiente não inventariado (R179-36) | o inventário lia PATH e /proc fora da pasta do pedido e contaminava a E11 | não observado: nenhuma partida seguinte tinha pedido que deixasse sondar o host | sem efeito observado |
| M24 | `fundacao-ia-multiprojetos/assets/fundacao-kit/fundacao/cli_conhecimento.py` e `fundacao-ia-multiprojetos/SKILL.md` | comando `python -m fundacao conhecimento listar\|buscar`, com a autorização do servidor MCP; a regra 2 da seção 3 aponta o comando (R179-37) | E7/C2 na coorte-12: a CLI não tinha como pedir o conteúdo pelo serviço, e a negativa não ficava na trilha | coorte-13: E7 da candidata 3 de 3, com a negativa registrada; testes do kit com mutantes | ajudou |
| M25 | `fundacao-ia-multiprojetos/SKILL.md` | a linha do topo do §1 vale só no pedido de auditoria de segurança ou revisão de segurança, com negativa para os demais; a regra do `cd` vale para todos e os comandos na raiz usam subshell (R179-34, R179-38) | com a R179-34, 15 de 16 partidas da candidata começavam pelo esqueleto em qualquer caso, e a E10 reprovou (coorte-13) | coorte-14: a primeira partida não leu o esqueleto, mas o portão E9 reprovou por Glob com `*` na raiz, que o esqueleto cobria | confundido |

## O que a versão traz

- Escolha de modelo por tipo de tarefa: a política de rotas `fundacao.route/2` associa a cada tipo de tarefa alvos
  ordenados com rota, provedor, modelo e esforço; tetos em Decimal antes do despacho; recusa sem mecanismo financeiro
  preventivo por chamada; a trilha separa modelo pedido e modelo observado. Implementada e testada, mas desligada: a
  política distribuída continua `/1`, só a rota simulada vem ligada e o R13 segue `implementado_inativo`.
- Análises estáticas do Ruflo e do codex-plugin-cc, com fontes fixadas (`entrega/propostas/`), e o desenho do piloto
  local × remoto (Qwen, Haiku e Opus), não executado.
- Harness²: P7, juiz cego de outro provedor (`evals/juiz_codex.py`: preparo, validação e comparação de notas), e P8,
  tipo lição na memória do projeto, com busca por gatilho; os P1 a P6 vieram na 1.7.7.
- Kit: `conhecimento listar` e `conhecimento buscar`, livro de cópias assinado pelo titular (modo estrito optativo),
  rotas com modelo e esforço, correções D1 a D3 da 1.7.8 e respostas uniformes para ID alheio nas lições.
- Host: pin do Python pela impressão do certificado da PSF e sinais de compactação e de status, distribuídos como
  modelos, sem ativação automática.
- Rotina: `scripts/verificar_fundacao.py` agrega as conferências e distingue não medido e não rodado de aprovado.
- Auditoria de segurança somente leitura: esqueleto `assets/templates/AUDITORIA-SEGURANCA.md`, conferidor
  `scripts/verificar_revisao_seguranca.py` e regras de evidência por afirmação.
- Regras do corpo da SKILL.md: aviso de instrução indevida em dados com fonte e ação recusada, pedido de conteúdo
  pelo serviço, inventário só com escopo, busca com poda, diretório do shell fora da fundação e esqueleto da
  auditoria só no pedido de auditoria.

## Estado da liberação e limites conhecidos

A bateria comportamental (regra B) não fechou e foi encerrada pelo titular em 26/10/2026, que pediu publicar uma
versão funcional e levar os problemas para a 1.7.10. A liberação exige suítes e conferências verdes nos dois
sistemas, revisão de segurança da versão, CI pública verde e os três destinos conferidos; não afirma que a bateria
passou. Na revalidação pelo Claude (32 partidas, executor Sonnet), aprovadas pelo parecer independente:

- E9 da candidata: 6 de 7 (as 6 nas coortes 12 e 13; a falha, na coorte-14, por Glob com `*` na raiz);
- E7 da candidata: 3 de 4 (a falha, antes do comando `conhecimento`);
- E13: candidata 2 de 2, base 2 de 2; E10: base 1 de 1, candidata 0 de 1 (antes da R179-38, sem nova medida);
- E11: candidata 1 de 13, base 0 de 2; E3 e E12 não rodaram nesta fase.

Para a 1.7.10: a SKILL.md não diz que o Glob com padrão sem pasta desce em todas as subpastas; a E10 precisa de nova
medida depois da R179-38; a E11 não passa com o Sonnet pela régua atual; a política `/2` precisa de ensaio real e
decisão do titular para ligar uma rota; o piloto de modelos não rodou; o P4/P7 com juízes não rodou nesta fase; e os
achados baixos das revisões estão nos registros de cada correção.

## Lições

### L1 — Temporários de teste precisam ser independentes da fundação em uso
- Gatilho: teste cria uma fundação fictícia ou mede isolamento e distingue pasta livre de pasta protegida.
- Lição: use temporários próprios do sistema, fora de qualquer fundação; mantenha logs no projeto e preserve a proteção.
- Evidência: M1, M3; `fundacao-ia-multiprojetos/scripts/tests/test_revisao_seguranca_177d_validadores.py`; rodadas desta retomada detectaram a fundação real como ancestral dos temporários.
- Confiança: alta

### L2 — Regra no topo da SKILL.md vira instrução para qualquer pedido
- Gatilho: uma correção para um caso entra no começo do corpo, antes dos passos, que o agente lê em todo pedido.
- Lição: escreva a condição e a negativa para os demais pedidos ("só no pedido de...; nos demais, não") e confira
  nos rastros a primeira ação de cada caso; a regra que sobra para todos (como a do `cd`) precisa caber nos fluxos que
  mandavam fazer o contrário.
- Evidência: M25; `fundacao-ia-multiprojetos/SKILL.md` §1 e
  `fundacao-ia-multiprojetos/scripts/tests/test_verificar_revisao_seguranca.py`; com a frase sem condição, 15 de 16
  partidas da candidata começaram pelo esqueleto da auditoria em casos que não eram auditoria, e a E10 reprovou; com a
  condição, a primeira partida seguinte começou pelo próprio caso.
- Confiança: média

### L3 — Cada critério exige sua própria evidência
- Gatilho: ensaio combina obrigações distintas ou relatório mistura observações e condições não verificadas.
- Lição: registre evidência, escopo e condições de cada afirmação antes de redigir; derive títulos e resumo desse quadro. Proteção de dados não demonstra aviso, condição não verificada não é ausência, e teste textual não demonstra comportamento.
- Evidência: M17, M18, M19; E9/C3 e E11/C4 em `fundacao-ia-multiprojetos/evals/evals.json` e regra em `fundacao-ia-multiprojetos/SKILL.md` §3.2; na oitava rodada, E9 preservou os dados e produziu o relatório, mas omitiu o aviso obrigatório (R179-22); na nona, E11 preservou arquivos/eventos e apresentou hipótese como fato (R179-23), motivando a conferência em `fundacao-ia-multiprojetos/assets/templates/REVISAO-SEGURANCA.md`; na décima, essa regra foi lida mas não aplicada consistentemente (R179-24), levando ao quadro obrigatório antes da redação. A confiança alta é no diagnóstico e no princípio de vincular afirmações à evidência; a eficácia do quadro ainda não foi medida.
- Confiança: alta
