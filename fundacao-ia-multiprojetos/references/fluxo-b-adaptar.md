# Fluxo B — Adaptar um projeto existente à fundação

Objetivo: trazer um projeto (ex.: OpenSquad, squads de agentes, scripts com IA,
um aplicativo) para a fundação **preservando funcionalidades, regras de negócio,
dados e integrações**, em passos pequenos, comparáveis e reversíveis. Método do
livro: diagnóstico A01–A02, decisão A04, referência A05, migração dos fluxos
jurídicos A22–A25 e engenharia reversa A26–A30 [Livro p8–p27, p115–p158];
técnicas nomeadas [3.0 R16.1]: caracterização (golden master), *parallel run*,
*strangler fig*, camada anticorrupção.

Pré-requisito: versão de fundação de destino identificada (se não houver, rode o
Fluxo A até A6). Cada etapa: **Entradas · Ações · Saídas · Critério · Falhas**.

## Ritmo: dois portões (padrão)

[Decisão; caso real de 2026-10-20: sete aceites, um por etapa, e o próprio titular pediu "completar
todas as etapas de B e deixar para eu revisar e assinar as decisões tudo ao final"; o lote B5–B10,
com um relatório que prende os arquivos por hash, funcionou sem perda de garantia.]

- **Portão 1 — análise e plano (B1–B5).** Rode B1→B5 em sequência, sem pedir "posso seguir?": nada
  aqui altera a origem nem executa código importado. Entregue de uma vez diagnóstico, mapa,
  compatibilidade, plano e contratos, mais a **folha de decisões** (`assets/templates/FOLHA-DE-DECISOES.md`)
  com tudo o que depende do usuário: mudanças intencionais de comportamento, executar código da
  origem numa cópia isolada (B6), importar segredos ou dados sensíveis, efeitos externos,
  componentes e o fluxo representativo do B2 (proponha o principal). Um aceite cobre o lote.
- **Portão 2 — execução e entrega (B6–B10).** Com o aceite do portão 1, rode B6→B10 em sequência e
  entregue um relatório único (esperado × observado por etapa, real × simulado, desvios do plano,
  hashes de cada arquivo entregue) para um aceite final.
- **Pare antes do portão** só se: a origem divergir do manifesto do B1; uma prova negativa falhar;
  surgir divergência que a B8 não classifique; a etapa precisar de algo fora do aceite (dado real
  novo, execução não autorizada, efeito externo, custo). Pare, registre e pergunte só aquilo.
- Etapa por etapa só se o usuário pedir. Paradas e perguntas seguem `references/comunicacao-leigo.md`.
- **Com a barreira de decisão assinada** (dados reais; `references/seguranca-isolamento.md` §2): uma
  assinatura por portão. A entrega do lote (o relatório que prende os arquivos por hash) fica em `outputs/`;
  a IA roda `python -m fundacao decisao preparar --projeto <p> --tarefa <id> --entrega outputs/<relatório>
  --tipo aceite --motivo "<palavras do titular>"`, passa ao titular os comandos de `para_o_titular` no cartão
  do §3 de `comunicacao-leigo.md` e, quando ele responder "assinado", roda sozinha `decisao registrar --arquivo
  <decisão>` e `tarefa concluir --decisao <decisão>`. Pedido de correção: `--tipo correcao` sobre a mesma
  entrega, assinado e registrado; a versão corrigida sai ao lado (v2; a v1 fica) e ganha um aceite novo — o
  aceite anterior deixa de concluir a tarefa. Rejeição: `--tipo rejeicao`.

## Sumário
- Diagnóstico: B1 inspeção · B2 mapa de funcionamento · B3 compatibilidade
- Planejamento: B4 inventário de decisões · B5 contratos a preservar · B6 referência e caracterização
- Implementação e comparação: B7 mudanças pequenas · B8 comparação antes/depois · B9 reexecução segura
- Encerramento: B10 entrega e reversão

---

## Diagnóstico

### B1 — Inspeção sem alteração [Livro A01–A02 p8–15]
**Entradas:** caminho do projeto; instruções (AGENTS.md, CLAUDE.md, README, planos);
relatórios anteriores; escopo do que **não** pode ser lido (casos reais, cofres, credenciais).
**Ações:** inventário do ambiente (`<skill>/scripts/inspecionar_ambiente.py`); manifesto
com hash dos arquivos técnicos lidos (`<skill>/scripts/manifesto.py criar`) — não é backup;
estado do Git (não rastreados, modificados, índice) para não atribuir a um commit o
que só existe localmente [Livro p13]; leia arquitetura, código, dependências
(declaradas × instaladas), dados (onde, formato, quem escreve), integrações
(serviços, credenciais por **referência**), testes e configuração. Classifique a
leitura: integral · parcial · só listagem · inacessível.
**Saídas:** `DIAGNOSTICO.md`, `inventario.json`, manifesto.
**Critério:** toda conclusão aponta para o registro que a sustenta; nada fora de
`evidence/` foi alterado. **Falhas:** arquivo essencial não lido = lacuna material,
registre caminho e erro [Livro p11].

### B2 — Mapa de funcionamento [Livro A02 p12–15]
**Entradas:** `DIAGNOSTICO.md`, inventário e manifesto (B1); um fluxo representativo
escolhido com o usuário (ou o principal, se não houver resposta).
**Ações:** siga o fluxo da solicitação à entrega: entrada → processamento → agentes →
ferramentas → armazenamento → decisões humanas → saída. Para cada passagem: executor
real (chamada de código · instrução textual · ação manual · hipótese) e contrato.
Classifique o material em **regra de domínio · configuração · programa · plano ·
teste** (arquivos híbridos: classifique os trechos). Registre divergências produtor ×
consumidor (ex. didático: manifesto com agentes como objetos, leitor esperando lista
de strings [Livro p13]).
**Saídas:** `MAPA-FUNCIONAL.md` (`assets/templates/MAPA-FUNCIONAL.md`),
`INVENTARIO-COMPONENTES.json`, `REGRAS-A-PRESERVAR.md`.
**Critério:** toda etapa tem executor identificado ou lacuna explícita; cada
hipótese tem um teste decisivo para cópia isolada [Livro p14].
**Falhas:** "o agente faz tudo" → peça a decomposição real; "o banco garante
sigilo" → identifique a regra de autorização e quem consulta o banco; script
existente que ninguém chama → "presente, sem integração demonstrada" [Livro p14].

### B3 — Classificação de compatibilidade
**Entradas:** mapa (B2); versão explícita da fundação de destino e seus contratos;
`python <skill>/scripts/sinais_compatibilidade.py --raiz <origem>` (sinais objetivos).
**Ações:** compare o projeto com os contratos e classifique, justificando com evidências:

| Classe | Quando | Consequência |
|---|---|---|
| Integração direta | Já respeita contratos (identidade, entradas/saídas, estado, sem acesso fora do escopo); basta registro e configuração | Registrar como projeto/componente; testes de contrato |
| Adaptação por interfaces | Regras e programas úteis, mas formatos/chamadas divergem dos contratos | Adaptador (camada anticorrupção) sem alterar a origem; formato canônico + conversor do legado |
| Refatoração delimitada | Acoplamento impede isolamento ou retomada (ex.: caminhos absolutos, leitura fora da raiz, estado só na conversa, segredos no código) | Mudanças pequenas na cópia, com caracterização antes; escopo e reversão definidos |
| Bloqueio nas condições atuais | Falta acesso à origem, runtime/licença indisponível, dependência externa não autorizada ou custo de sustentar > migrar sem decisão | Requisito `bloqueado`; condição de resolução; etapas independentes seguem |

Critérios do livro para manter × reformular × substituir: adequação, manutenção,
isolamento, interoperabilidade, custo, observabilidade, evolução; "não investigado"
≠ 0; "simplicidade não se mede pelo número de arquivos apagados" [Livro p15, p21].
Sinais objetivos de refatoração/bloqueio: caminhos absolutos ou `..` saindo da
raiz, leitura de pastas de outros clientes, credenciais em código, efeitos
externos sem chave de idempotência, ausência de qualquer forma de teste.
**Saídas:** classe escolhida com justificativa e evidências na seção de compatibilidade
do `DIAGNOSTICO.md`; requisitos afetados na matriz.
**Critério:** a classe aponta para sinais e trechos concretos; o valor de credenciais
nunca aparece no relatório (cite arquivo e linha).
**Falhas:** sinais contraditórios → escolha a classe mais conservadora e registre o teste
que mudaria a decisão; origem inacessível em parte → classe provisória + lacuna.

---

## Planejamento

### B4 — Inventário de decisões [Livro p13, p15]
**Entradas:** mapa (B2), classe (B3), regras a preservar.
**Ações:** para cada item: **preservar · adaptar · corrigir · substituir · investigar**,
com motivo e o teste que comprova. "Substituir" não é "apagar": a regra de negócio
sobrevive à troca do programa. Duplicatas (ex.: exportador copiado em três squads,
um com campo extra) não se unificam antes de saber se a diferença é legítima
[Livro p15]. Modelo: `assets/templates/PLANO-ADAPTACAO.md`.
**Saídas:** `PLANO-ADAPTACAO.md` com a decisão por item.
**Critério:** todo item tem decisão, motivo e teste; decisões que mudam comportamento
estão marcadas para aprovação do usuário e entram na folha de decisões do portão 1.
**Falhas:** item sem evidência suficiente → "investigar" com o teste decisivo, nunca
"substituir" por suposição; decisão de negócio fora do escopo → prepare as opções e pergunte.

### B5 — Contratos e comportamentos que devem permanecer válidos
**Entradas:** plano (B4); entradas, saídas e efeitos observados na origem.
**Ações:** liste entradas, saídas, erros (códigos e mensagens), formatos, dados (esquema,
volume, retenção) e efeitos externos (envios, arquivos, chamadas) que precisam
continuar idênticos. **Separe** mudanças intencionais de comportamento (com quem
aprovou e nova versão de contrato) das alterações exclusivamente técnicas [Livro
p149–p150: refatoração preserva v1; regra nova cria v2]. Distinga alteração de
**código**, **migração de dados** e **mudança de infraestrutura** — cada uma tem
plano de retorno próprio (reverter código não reverte o banco) [Livro p168].
**Saídas:** seção "Contratos preservados" do plano (ou `CONTRATO.schema.json` por interface).
**Critério:** cada contrato tem um teste que o verifica; mudanças intencionais têm
aprovador e versão.
**Falhas:** contrato implícito descoberto depois → acrescente o teste antes de seguir;
efeito externo sem idempotência → trate como risco e isole com mock na comparação.

### B6 — Referência recuperável e testes de caracterização
**Entradas:** origem (somente leitura); contratos (B5); entradas representativas e de erro.
**Ações**
1. Referência (Fluxo A, etapa A4): manifesto, cópia fora do Git, SQLite por backup
   (`python <skill>/scripts/backup_sqlite.py`), receita de ambiente; restauração ensaiada.
2. Caracterização proporcional ao risco: grave o comportamento ATUAL para entradas
   conhecidas, inclusive erros e casos-limite, **antes** de mudar:
   `python <skill>/scripts/caracterizar.py gravar --entradas "fixtures/*.json" --saida golden.json --cwd <copia> -- python app.py {entrada}`.
   Use `--ignorar` para campos voláteis (datas). Inclua casos negativos (entrada
   inválida deve continuar rejeitada) [Livro p137, p153]. [Decisão; auditoria externa da
   1.3.4] A comparação usa o hash das saídas INTEIRAS (o golden guarda só um trecho para
   leitura) e os efeitos de cada caso na pasta de saída — arquivos escritos ou removidos por
   aquele caso, separados dos que já estavam lá. Programa que grava em pasta própria: use
   `--ensaio <pasta-nova>` e `{ensaio}` no comando; a ferramenta cria a pasta (com marca),
   limpa só ela entre casos e recusa pasta existente sem a marca. Manifesto da origem com
   exclusões próprias: `manifesto.py criar ... --excluir <glob>` grava a política, e
   `verificar` reusa a mesma (mudar a política exige `--mudar-politica`, relatada à parte).
3. Para regras com muitas entradas, acrescente propriedades metamórficas (ex.:
   reordenar itens preserva o total) [Livro p145].
**Saídas:** referência com manifesto; `golden.json`; propriedades metamórficas, se houver.
**Critério:** restauração ensaiada; golden cobre caminhos felizes, erros e limites; a
origem continua idêntica ao manifesto.
**Falhas:** comportamento não determinístico → `--ignorar` com justificativa ou
repetição para medir variação; efeito externo real no ensaio → isole (rede bloqueada,
mock rotulado) antes de gravar.

---

## Implementação e comparação

### B7 — Mudanças pequenas e verificáveis
**Entradas:** plano (B4), contratos (B5), golden (B6), fundação de destino.
**Ações**
- Trabalhe numa **cópia** ou área de mudança (ex.: `git worktree`), nunca na origem
  [Livro p151]. Preserve alterações locais e particularidades legítimas.
- Aproveite componentes existentes compatíveis; introduza adaptadores em vez de
  reescrever (ex.: formato canônico + adaptador do manifesto legado; o painel lê o
  canônico).
- Registre o projeto na fundação pelo modelo (identidade, configuração, ACL,
  armazenamento próprio); dados particulares ficam no projeto/caso.
- Exponha o programa legado como **componente** registrado (habilitação,
  autorização, timeout, versão) — `references/capacidades/08-ferramentas-hooks-mcp-skills-plugins.md`.
- O código que o componente executa fica na fonte da fundação, nunca nos dados do projeto; o
  módulo traz o manifesto (sha256 de cada arquivo do código, sem nenhum a mais ou a menos),
  confere-o imediatamente antes de cada execução e roda uma cópia privada conferida; habilite
  com `componente habilitar`, que grava o `entrypoint_sha256` [varredura da 1.4.5, #6].
- Uma mudança por vez; após cada uma rode a caracterização e os testes de contrato.
**Saídas:** mudanças registradas (arquivo, tipo, motivo, reversão); projeto e componente
registrados; RETOMADA atualizada a cada mudança.
**Critério:** cada mudança passa na caracterização e nos testes de contrato antes da
próxima; nenhum segredo copiado; origem intocada.
**Falhas:** divergência após uma mudança → reverta só ela e investigue; necessidade de
alterar o núcleo da fundação → prepare a correção com teste e peça decisão (afeta todos
os projetos).

### B8 — Comparação antes × depois
**Entradas:** golden (B6); versão adaptada (B7).
**Ações:** `python <skill>/scripts/caracterizar.py comparar --golden golden.json --cwd <nova> -- <comando>`.
Toda divergência é classificada: regressão (corrigir a camada responsável),
mudança intencional aprovada (atualizar especificação e versão do contrato) ou
diferença irrelevante justificada (ex.: ordem de chaves JSON fora do contrato)
[Livro p144]. Nunca ajuste o golden para "passar". Compare também isolamento
(negativas), retomada e custo quando aplicável. Igualdade de total sem igualdade
de linhas não basta [Livro p148].
**Saídas:** relatório de comparação com a classificação de cada divergência.
**Critério:** 0 regressões; mudanças intencionais com aprovação registrada.
**Falhas:** golden "ajustado" sem decisão → descarte o ajuste e reabra a divergência;
comparação impossível (ambiente diferente) → registre a lacuna e não declare equivalência.

### B9 — Reexecução segura (projeto parcialmente adaptado)
**Entradas:** `RETOMADA.md`; estado real (arquivos, registro, banco); golden.
**Ações**
- Antes de cada etapa, **detecte o que já existe**: projeto registrado, componente
  no registro, adaptador presente, migração aplicada (`PRAGMA user_version`),
  golden gravado, entradas da RETOMADA em "ações já realizadas".
- Atualize só o necessário; não duplique configuração, registros, dados ou efeitos
  (chaves de idempotência; "criar" que encontra instância existente informa e não
  substitui) [Livro p37].
- **Atualizar o modelo de projeto ≠ migrar instâncias já criadas**: compare
  `template_version` da instância com a atual; migração é explícita, com campo
  novo recebendo padrão e sem sobrescrever instruções locais revisadas [Livro p38].
- Divergência entre estado registrado e arquivos: reconcilie por identificador e
  hash; não aceite "qualquer arquivo encontrado" [Livro p47].
**Saídas:** lista de etapas "já existia" × "feito agora"; RETOMADA atualizada.
**Critério:** reexecutar não cria duplicatas (registro, eventos, arquivos) e uma terceira
passagem não muda nada.
**Falhas:** estado registrado diverge dos arquivos → reconcilie antes de agir; RETOMADA
desatualizada → confie no estado conferido e registre a divergência.

---

## Encerramento

### B10 — Entrega e reversão
**Entradas:** resultados de B6–B9; decisões pendentes.
**Ações:** entregue mapa das alterações (arquivo, tipo, motivo, reversão); resultados das
comparações (golden, negativas); limitações remanescentes; **procedimento de
reversão** testado em cópia; estado de compatibilidade **demonstrado** (classe da
B3 + evidências); matriz e RETOMADA atualizadas.
**Saídas:** `RELATORIO-FINAL.md` da adaptação (o relatório único do portão 2, com o hash de cada
arquivo entregue), procedimento de reversão, matriz e RETOMADA.
**Critério (regra de honestidade):** um projeto demonstrativo funcionando comprova o
cenário testado; **a migração do projeto original exige evidências próprias** sobre a
origem e seus comportamentos [Livro p118, p193, p212]. Fluxos distintos (ex.:
petição, honorários, proposta, contrato) têm cada um sua origem, implementação,
integração e evidência — o sucesso de um não conclui os outros [Livro p132].
**Falhas:** reversão não ensaiada → não declare a adaptação concluída; pendências de
decisão → liste com opções e consequências, sem "decidir pelo usuário".

---

## Exemplos de domínio (didáticos) para os testes de aceite

- **Jurídico (A22–A25):** pacote de petição com matriz fato/prova/tese/pedido e
  PENDÊNCIAS explícitas; teste sem D2 mantém a alegação de pagamento e cria pendência
  de prova; honorários com Decimal (660 → 880 com margem de 25% → 792 com 10% de
  desconto; margem 100% rejeitada); proposta com parcelas 316,80 + 316,80 + 158,40 =
  792,00 (parcelas antigas que somam 880 são rejeitadas); contrato que amplia o
  objeto para "representação em todas as instâncias" é rejeitado. Dados completos:
  `references/livro/m07-juridico.md`.
- **Software (A26–A30):** CaixaSim v1 (contrato JSON, erros E_*), documentação com
  evidências, implementação própria com inteiros escalados comparada em 60 casos,
  modernização em módulos com v2 (desconto) preservando v1, integração por adaptador
  com recusa de `price_kind: internal_cost`. Dados: `references/livro/m08-software.md`.
- **OpenSquad (migração real do usuário):** squad → skill + subagente + workflow com
  *parallel run* até equivalência medida por hash e rubrica [3.0 R16.7]; a origem
  continua intocada até a decisão de corte.
