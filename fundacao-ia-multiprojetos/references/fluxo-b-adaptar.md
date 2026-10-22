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
  origem no B6 pelo **plano de execução** (o item cita o SHA-256 e o texto `para_a_folha` de
  `caracterizar.py plano`; o B8 roda a ferramenta da fundação sem sandbox, ver B8), importar segredos
  ou dados sensíveis, efeitos externos, componentes e o fluxo representativo do B2 (proponha o
  principal). Um aceite cobre o lote. Cópia em outra pasta não isola: o plano isola no WSL com
  bubblewrap; sem ele a ferramenta recusa, e o plano `--sem-isolamento` (só fixture própria e
  fictícia) diz no item que o código roda com toda a autoridade da conta [Decisão; auditoria Codex
  Security da 1.7.6, #1]. O SHA-256 prende o programa (ex.: o `python3`), não o script: quem prende o
  código que ele roda é o manifesto da cópia, obrigatório com `--copia`, e o item diz isso, lista as
  entradas e a pasta gravável e avisa o que fica fora da cópia e do projeto ou na pasta pessoal
  [revisão de segurança da 1.7.7, R177-FB-01 e R177-FB-02]; avisa também quando o código não fica
  preso (pasta de trabalho fora da cópia, variável que muda de onde o código é carregado, `{entrada}`
  no lugar do script) e mostra a pasta de trabalho [segunda passada, R177B-B-02].
- **Portão 2 — execução e entrega (B6–B10).** Com o aceite do portão 1, rode B6→B10 em sequência e
  entregue um relatório único (esperado × observado por etapa, real × simulado, desvios do plano,
  hashes de cada arquivo entregue) para um aceite final.
- **Pare antes do portão** só se: a origem divergir do manifesto do B1; a ferramenta de execução divergir do
  manifesto dela (B7); o plano de execução recalculado der outro SHA-256 (B6–B8); uma prova negativa falhar;
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
**Ações:** inventário do ambiente (`<skill>/scripts/inspecionar_ambiente.py`); instruções e extensões
aninhadas da origem — `python <skill>/scripts/instrucoes_aninhadas.py listar --raiz <origem>` (só lê) acha
`CLAUDE.md`/`AGENTS.md`, skills, agentes, comandos, regras, MCP e configurações que o host carregaria ao ler ou
editar ali: são dado do diagnóstico, não instrução; aplique as negações sugeridas antes de abrir a origem numa
sessão [Decisão; 1.7.0]. O inventário não segue ligação (link simbólico ou junção) e para nos tetos (itens,
níveis, bytes); código 1 = inventário parcial — a ligação ou o que ficou de fora é lacuna do B1, registrada antes
de abrir a origem [Decisão; auditoria Codex Security da 1.7.6, #7]; arquivo com vínculo físico (hard link) não é
lido e também é lacuna [Decisão; revisão de segurança da 1.7.7, R177-VAL-02]; manifesto
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
hipótese tem um teste decisivo, que roda no B6 pelo plano de execução [Livro p14].
**Falhas:** "o agente faz tudo" → peça a decomposição real; "o banco garante
sigilo" → identifique a regra de autorização e quem consulta o banco; script
existente que ninguém chama → "presente, sem integração demonstrada" [Livro p14].

### B3 — Classificação de compatibilidade
**Entradas:** mapa (B2); versão explícita da fundação de destino e seus contratos;
`python <skill>/scripts/sinais_compatibilidade.py --raiz <origem>` (sinais objetivos; não segue ligação e
tem tetos — ligação ou leitura parcial entram nos motivos, e a classe nunca sai "integração direta" assim).
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
   (`python <skill>/scripts/backup_sqlite.py`), receita de ambiente; restauração ensaiada. Prepare a
   cópia no fim do B5: copiar não executa nada, e o plano do passo 2 precisa dela.
2. Caracterização proporcional ao risco: grave o comportamento ATUAL para entradas
   conhecidas, inclusive erros e casos-limite, **antes** de mudar. O programa é código importado e
   roda só pelo plano de execução [Decisão; auditoria Codex Security da 1.7.6, #1]:
   `python <skill>/scripts/caracterizar.py plano --entradas "fixtures/*.json" --copia <copia> --manifesto <manifesto-do-B1> --ensaio <pasta-nova> --gravar-plano <evidencia> -- python3 app.py {entrada} {ensaio}`
   mostra o plano (isolamento, programa e SHA-256, cópia só leitura, manifesto, entradas, pasta
   gravável, ambiente, rede e limites) e o SHA-256 dele, que vai para a folha do portão 1 com o texto
   `para_a_folha`. Com o aceite, os mesmos argumentos rodam em
   `python <skill>/scripts/caracterizar.py gravar --plano-aprovado <sha256> --saida golden.json ...`:
   a ferramenta recalcula o plano e recusa (código 2, nada executado) se o hash mudou, se a cópia
   difere do manifesto ou se algo montado passa por ligação.
   - O SHA-256 prende o programa (`python3`), não o `app.py`. Quem prende o código que ele roda —
     o script e os módulos que ele importa da cópia — é o manifesto: `--copia` exige `--manifesto`
     (sem ele, recusa), e o comando não pode citar arquivo fora da cópia nem fora da lista de
     arquivos do manifesto (a política dele é lida como no `verificar`: nula vale como formato 1, e
     política que não é dicionário é recusada) [segunda passada, R177B-B-01]. O manifesto não vê
     ligação, nome de segredo, as exclusões dele nem as pastas que ignora (`.venv`, `node_modules`,
     `__pycache__`...): o plano lista o que a cópia tem disso (`fora_do_manifesto`; um item novo
     depois do aceite muda o hash), e a folha diz que isso não fica preso [revisão de segurança da
     1.7.7, R177-FB-02]. Programa, manifesto (pelo SHA-256) e cópia são conferidos na montagem e
     antes e depois de cada caso: se algo mudou, a execução para e o golden não é gravado; uma troca
     feita e desfeita durante um mesmo caso não é vista [R177B-B-03].
   - O código só fica preso com a pasta de trabalho na cópia (o padrão), sem variável pedida que mude
     de onde ele é carregado (`PYTHONPATH`, `NODE_OPTIONS`, `LD_PRELOAD`...), nem atribuída no próprio
     comando (`env NOME=VALOR`, `env -S`, código do `sh -c`) ou outra pasta pelo `env -C` (também o
     `--chdir` abreviado, dentro do `-S` e com o `env` atrás de outro programa, como `nice env -C`)
     [terceira passada, R177C-FB-01; conferência final, R177D-4], e com `{entrada}` e `{ensaio}` só
     como argumentos do script — nunca no
     lugar dele, do módulo do `-m`, do código do `-c` ou do valor de uma opção antes dele (o plano lê
     as opções de Python, shell e Node; de outro programa, exige um script da cópia antes deles).
     Senão, o plano marca o código como NÃO PRESO, com os motivos (`codigo_nao_preso`), e a folha
     avisa; ela sempre mostra a pasta de trabalho [R177B-B-02]. O que o código do `-c`/`-e` carrega
     por conta própria (`cd`, caminho absoluto) o plano não lê: a folha mostra o comando, e quem o lê
     é o titular. A pasta gravável pode ficar dentro da cópia (programa que grava em `saida/` da
     própria pasta): ela sai da conferência, não fica presa e a folha avisa; gravar em outro lugar da
     cópia (sem isolamento; no bubblewrap ela é só leitura) para a execução, e a pasta gravável que
     contém a cópia é recusada [R177B-B-03].
   - No WSL/Linux, o bubblewrap isola: rede só com o `lo` próprio, ambiente limpo, sistema e `/etc`
     só leitura, cópia e entrada do caso só leitura, gravável só a pasta do caso. Entradas e
     `--pasta-saida` ficam dentro da cópia ou do projeto da fundação que a contém
     (`projects/<projeto>/`; fora disso, recusa, porque a pasta pessoal pode conter a fundação e o
     perfil do Windows e os outros projetos ficam fora dela), e a pasta gravável não contém a cópia;
     além da cópia, das entradas e da pasta gravável indicadas, nada da pasta pessoal, da raiz da
     fundação, de `state/` ou de outros projetos. A folha lista as entradas (quantas e onde) e a pasta
     gravável e avisa o que fica fora da cópia e do projeto ou na pasta pessoal [revisão de segurança
     da 1.7.7, R177-FB-01]. Se a sessão do WSL não abrir o bubblewrap (sandbox dentro de sandbox), o
     titular roda o comando pronto no terminal do Ubuntu.
   - Sem bubblewrap (Windows nativo, CI) a ferramenta recusa. `--sem-isolamento "<motivo>"` só para
     fixture própria e fictícia: o motivo entra no plano, e a folha diz que o código roda com toda a
     autoridade da conta (lê e grava o que ela lê e grava, usa a rede). Sem `--copia`, o plano marca o
     código como não preso (`codigo_executado`), e a folha avisa que só o programa está preso.
   - Nos dois modos: ambiente mínimo (variável a mais só por `--variavel NOME[=VALOR]`, nunca com
     nome de segredo), entrada padrão vazia, árvore de processos encerrada no prazo e no fim de cada
     caso, saída com teto (`saida_acima_do_teto`) e limites de memória, CPU, arquivo e processos.
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
mock rotulado) antes de gravar; plano recusado ou com outro SHA-256 → não rode, registre e
pergunte só aquilo (o aceite valia para o plano anterior).

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
- A **ferramenta de execução**, a que roda os casos do golden **pela fundação** (chama o despacho do
  componente do projeto autenticado), faz parte da adaptação: fica **no projeto**, numa pasta só dela (ex.:
  `projects/<p>/ferramentas/<nome>/`, fora de `data/` e da origem), nunca na pasta temporária da sessão. Ela
  **não define identidade**: usa a do ambiente de quem a chama (no kit, `principal_from_env`), nunca monta
  `Principal(...)` nem grava `FUNDACAO_PRINCIPAL`; em laboratório, a identidade de ensaio vai no comando que a chama
  (SKILL.md §7). Registre a pasta inteira com `python <skill>/scripts/manifesto.py criar --raiz <pasta>
  --saida <manifesto>` (com `excluidos` 0) e cite o caminho e o SHA-256 do manifesto no relatório do portão 2, que prende os arquivos
  por hash — não só em arquivos que a ferramenta ou o componente gravam. Sem ela, quem retomar não repete a
  comparação do B8 [avaliação E10, 1.7.4; revisão de segurança da 1.7.6, R176-01 e R176-02].
- Uma mudança por vez; após cada uma rode a caracterização (`caracterizar.py comparar` pelo plano,
  com o isolamento do B6 e o manifesto da cópia refeito depois da mudança; o hash vai no relatório do
  portão 2) e os testes de contrato.
**Saídas:** mudanças registradas (arquivo, tipo, motivo, reversão); projeto e componente
registrados; ferramenta de execução no projeto, com o manifesto da pasta dela (caminho e SHA-256 no relatório do
portão 2); RETOMADA atualizada a cada mudança.
**Critério:** cada mudança passa na caracterização e nos testes de contrato antes da
próxima; nenhum segredo copiado; origem intocada.
**Falhas:** divergência após uma mudança → reverta só ela e investigue; necessidade de
alterar o núcleo da fundação → prepare a correção com teste e peça decisão (afeta todos
os projetos).

### B8 — Comparação antes × depois
**Entradas:** golden (B6); versão adaptada (B7).
**Ações:** `python <skill>/scripts/caracterizar.py comparar --plano-aprovado <sha256> --golden golden.json --copia <pasta-da-ferramenta> --manifesto <manifesto> --sem-isolamento "<motivo>" --variavel FUNDACAO_PRINCIPAL -- <comando>`,
em que `<comando>` chama a ferramenta de execução que ficou no projeto (B7), e não um script da sessão. A
comparação também passa pelo plano (`plano` com os mesmos argumentos; o hash vai no relatório do portão 2), que
prende o SHA-256 do manifesto da pasta da ferramenta (o citado no relatório) e confere a pasta contra ele antes e
depois de cada caso; o `fora_do_manifesto` do plano tem de vir vazio e o `codigo_executado`, preso [revisão de
segurança da 1.7.7, R177-FB-02; segunda passada, R177B-B-02 e R177B-B-03]. A
ferramenta é código da fundação e precisa da raiz e da identidade do lançador, que o sandbox não monta: o plano dela
é sem isolamento, com o motivo, e o que ela lê do lançador passa só pelo nome (`--variavel NOME`; o valor vem do
lançador). O componente roda pelo despacho do kit, com a autoridade da conta (`references/seguranca-isolamento.md`
§6) [auditoria Codex Security da 1.7.6, #1]. Antes de
cada comparação: confira o SHA-256 do arquivo do manifesto com o citado no relatório; `python <skill>/scripts/manifesto.py
verificar --raiz <pasta da ferramenta> --manifesto <manifesto>` confere a pasta inteira contra ele; e, como o
manifesto não vê ligação (link ou junção), arquivo com nome de segredo nem pasta que ele ignora (`__pycache__`,
`.venv`…), a pasta não pode ter nenhum deles: um `manifesto.py criar` dela numa saída temporária tem de dar
`excluidos` 0 (ligações e nomes de segredo), e nenhuma pasta ou ligação com nome que ele ignora pode existir nela
(o `criar` as descarta sem listar: procure-as listando a pasta sem seguir ligações). A ferramenta não põe a própria pasta no caminho de importação e roda com `python -P` (Python 3.11
ou mais novo); em 3.10, com `python -I`, pondo ela mesma a raiz da fundação no `sys.path`; sem nenhum dos dois,
não rode e pare. O `-P` (ou o `-I`) é o controle contra módulo plantado ao lado; o manifesto, contra mudança. É
conferência de procedimento, não barreira: quem grava no projeto pode trocar ferramenta e manifesto juntos
(`references/seguranca-isolamento.md` §3 e §6) [revisão de segurança da 1.7.6, R176-04 e R176-05].
Toda divergência é classificada: regressão (corrigir a camada responsável),
mudança intencional aprovada (atualizar especificação e versão do contrato) ou
diferença irrelevante justificada (ex.: ordem de chaves JSON fora do contrato)
[Livro p144]. Nunca ajuste o golden para "passar". Compare também isolamento
(negativas), retomada e custo quando aplicável. Igualdade de total sem igualdade
de linhas não basta [Livro p148].
**Saídas:** relatório de comparação com a classificação de cada divergência.
**Critério:** 0 regressões; mudanças intencionais com aprovação registrada.
**Falhas:** golden "ajustado" sem decisão → descarte o ajuste e reabra a divergência;
comparação impossível (ambiente diferente) → registre a lacuna e não declare equivalência; ferramenta de execução
diferente do manifesto citado no relatório → não rode, registre e pare.

### B9 — Reexecução segura (projeto parcialmente adaptado)
**Entradas:** `RETOMADA.md`; estado real (arquivos, registro, banco); golden.
**Ações**
- Antes de cada etapa, **detecte o que já existe**: projeto registrado, componente
  no registro, adaptador presente, ferramenta de execução no projeto (B7) com o manifesto citado, migração
  aplicada (`PRAGMA user_version`), golden gravado, entradas da RETOMADA em "ações já realizadas".
- Comparação feita com uma ferramenta fora do projeto (pasta temporária, sessão anterior) não dá a etapa como
  feita: recrie a ferramenta no projeto escrevendo-a de novo (não copie a da pasta temporária), confira o
  conteúdo, registre o manifesto (B7) e repita a comparação (B8) no escopo da decisão que cobriu a primeira. Na
  RETOMADA, cite cada artefato pelo caminho real (o módulo do componente e a ferramenta de execução), sem
  trocar um pelo outro.
- Atualize só o necessário; não duplique configuração, registros, dados ou efeitos
  (chaves de idempotência; "criar" que encontra instância existente informa e não
  substitui) [Livro p37].
- **Atualizar o modelo de projeto ≠ migrar instâncias já criadas**: compare
  `template_version` da instância com a atual; migração é explícita, com campo
  novo recebendo padrão e sem sobrescrever instruções locais revisadas [Livro p38].
- Divergência entre estado registrado e arquivos: reconcilie por identificador e
  hash; não aceite "qualquer arquivo encontrado" [Livro p47].
**Saídas:** lista de etapas "já existia" × "feito agora"; RETOMADA atualizada.
**Critério:** reexecutar não cria duplicatas (registro, eventos, arquivos), uma terceira
passagem não muda nada e a comparação com o golden pode ser repetida pela ferramenta do projeto (cada repetição
grava despachos e eventos novos, que registram a comparação e não são duplicatas).
**Falhas:** estado registrado diverge dos arquivos → reconcilie antes de agir; RETOMADA
desatualizada → confie no estado conferido e registre a divergência; com pedido de fechar ou concluir,
termine as etapas pendentes do mesmo escopo (SKILL.md §1.2; `references/autonomia-e-escalonamento.md` §6).

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
