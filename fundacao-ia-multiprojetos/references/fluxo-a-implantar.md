# Fluxo A — Implantar a fundação e criar projetos

Cada etapa traz **Entradas · Ações · Saídas · Critério de conclusão · Falhas e
tratamento**. Atualize `RETOMADA.md` e a matriz ao fim de cada etapa. Origem:
Módulos 01–02 do livro [Livro p8–p39], capacidades nos Módulos 03–10, reordenação
em trilhas [3.0 §5.1].

**Ritmo** [Decisão; implantação real de 2026-10-19/20]: colete as escolhas do usuário de uma vez,
no início, com `assets/templates/FORMULARIO-IMPLANTACAO.md` (item em branco = padrão seguro), e
encadeie A1→A8 sem pedir confirmação entre etapas. Volte ao usuário só pelo que depende dele por
natureza (senha, administrador, contas e cobrança, custo acima do teto, dados reais), num cartão de
parada — `references/comunicacao-leigo.md`.

## Sumário
- A1 Ambiente, instruções, recursos e fundação anterior
- A2 Objetivos, restrições, critérios e arquitetura
- A3 Alternativas e decisões registradas
- A4 Referência recuperável
- A5 Núcleo e capacidades por etapas (ordem recomendada)
- A6 Modelo reutilizável de projeto
- A7 Dois projetos distintos: reutilização e isolamento
- A8 Entrega, operação e retomada
- §Host Preparo da máquina para dados reais (Windows e WSL2)
- §Kit Comandos do kit de referência

---

## A1 — Ambiente, instruções, recursos e fundação anterior [Livro A01 p8–11, A03 p16–19]

**Entradas:** pedido do usuário e escopo fixado (SKILL.md §1); pasta autorizada; `RETOMADA.md`/relatórios
anteriores (estado e evidências, não autorização); `AGENTS.md`/`CLAUDE.md`.

**Ações**
1. `python <skill>/scripts/inspecionar_ambiente.py --pasta <raiz> --somente-localizar` — não executa
   programas nem grava. Sem `--somente-localizar`, roda `--version` de CLIs (claude, codex, git…),
   `py -0p`/`pymanager list` e `wsl --list` (lista; não inicia WSL): só se o escopo permitir executar
   CLIs. `--saida <raiz>/evidence/ambiente/inventario-<data>.json` grava (exige escrita autorizada;
   recusa arquivo existente) [auditoria da 1.4.1, A18]. Nunca instala nem lê credenciais. Confira
   `pasta.sistema_de_arquivos` (exFAT/FAT = sem permissões do SO).
2. Leia as instruções aplicáveis e classifique o acesso: Windows nativo, WSL ou remoto.
3. Procure fundação anterior: `registry/`, `state/state.sqlite`, pacote `fundacao/`,
   `registry/kit_install.json`, `evidence/`. Se existir, este fluxo vira **extensão**:
   leia inventário e matriz e continue do último estado confirmado (não recrie).
4. Mapeie acessos sem ler segredos (A03): para cada ferramenta/provedor registre
   `provider_id`, canal (sessão assistida · CLI/SDK oficial · API), modo de
   autenticação observável, escopo, estado, evidência e limites. Assinatura, CLI,
   API e SDK são regimes diferentes; consulte `references/capacidades/03-provedores-modelos.md`.
5. Defina orçamento de laboratório: teto de chamadas reais (padrão 4), regra de
   parada e despesas possíveis; valores desconhecidos ficam "não medido".

**Saídas:** `evidence/ambiente/inventario-<data>.json` (com escrita autorizada), `DIAGNOSTICO.md` (seções 1, 6, 7),
`ACESSOS.json`, `ORCAMENTO.md`, `PERMISSOES.md` (leitura × gravação × ação externa;
onde a autorização será aplicada fora do modelo).

**Critério:** itens essenciais respondidos ou bloqueios precisos; nada alterado fora de `evidence/`.

**Falhas:** sessão sem acesso à máquina → relatório útil + prompt para a sessão
certa [Livro p10]; algo foi instalado durante o diagnóstico → listar alterações,
reverter com segurança e voltar ao escopo de leitura [Livro p11]; Python ausente é
achado, não ordem de instalar (o gerenciador pode instalar sozinho ao lançar `python`)
[Livro p8–9; Verificado 2026-10-18].

## A2 — Objetivos, restrições, critérios e arquitetura [Livro A04 p20–23]

**Entradas:** saídas de A1; objetivos do usuário; projetos pretendidos.

**Ações**
1. Escreva `MISSION.md`: objetivo, resultados, limites, critérios de aceite [Livro p204].
2. Distribua responsabilidades: núcleo (tarefas, autorização, resultados, estado,
   evidências) · adaptadores (provedores/ferramentas) · projetos (regras de domínio)
   · casos (dados particulares). Nenhum dado de caso no núcleo [Livro p20].
3. Liste os contratos: tarefa, resultado, provedor, ferramenta, memória, evidência,
   projeto, componente (`assets/templates/CONTRATO.schema.json` como modelo).
4. Justifique armazenamento e execução pelo ambiente real. SQLite + arquivos é a
   composição didática; mais de uma máquina/usuário escrevendo ou corpus grande →
   preserve contratos e troque o armazenamento (ex.: Postgres) [Livro p21; 3.0 R2.10].
5. Classifique capacidades em trilha **essencial** e **avançada** [3.0 §5.1] sem
   remover nenhuma: todas ficam na matriz; a ativação acompanha a necessidade do projeto.
6. Inicialize a matriz: `python <skill>/scripts/matriz.py init --saida <raiz>/registry/requisitos.csv`.

**Saídas:** `MISSION.md`, `ARQUITETURA.md`, `registry/requisitos.csv`.

**Critério:** cada componente com uma responsabilidade; nenhuma regra de cliente
no núcleo; custos/acessos indisponíveis explícitos [Livro p23].

**Falhas:** preferência inicial tratada como decisão → exija o teste capaz de refutá-la.

## A3 — Alternativas e decisões registradas [Livro A04 p20–23, A04B p24–27; 3.0 R3]

**Entradas:** `MISSION.md`, `ARQUITETURA.md` e matriz (A2); inventário e acessos (A1);
sistema existente, se houver.

**Ações**
1. Se houver sistema existente, compare manter · reformular por partes · substituir
   com pesos definidos **antes** de avaliar (escala 0–4, "não investigado" ≠ 0)
   [Livro p21]; modelo: `assets/templates/DECISAO.md`.
2. Orquestração: compare ao menos duas abordagens viáveis — núcleo próprio (kit),
   LangGraph + persistência SQLite, DBOS em SQLite, CrewAI Flows, Microsoft Agent
   Framework, Pydantic AI/OpenAI Agents SDK/Claude Agent SDK [Livro p24; 3.0 R3.1].
   Abra fontes oficiais, registre versão/commit, licença e data; estrelas não provam
   adequação [Livro p21, p25].
3. Protótipo discriminante, mesmo cenário nas duas: normalização → provedor
   **simulado** → artefato → revisão; injete falha **após** gravar o artefato e
   antes de confirmar a tarefa; retome; troque o adaptador; tente ler projeto sem
   acesso [Livro p25]. Compare efeitos, não só tempo; rotule simulações.
4. Instalações novas só depois de A4 e no ambiente isolado autorizado.

**Saídas:** `DECISAO-001.md` (arquitetura), `DECISAO-002.md` (orquestração),
`MATRIZ-ALTERNATIVAS.md`, protótipos, evidências.

**Critério:** fontes primárias datadas; mesmo cenário nas duas abordagens; falhas
observáveis; decisão ligada aos requisitos R01, R03, R05 [Livro p26].

**Falhas:** só uma opção executável → mantenha a comparação documental e o
experimento restante pendente [Livro p26]; protótipo A mais rápido porque não
grava estado → compare só após equalizar serviços prestados [Livro p27]; instalar
uma alternativa exige autorização → prepare o comando e a pasta isolada e pergunte.

## A4 — Referência recuperável [Livro A05 p28–31]

**Entradas:** raiz atual (vazia ou com fundação anterior); decisões de A3; lista do
que é canônico × reconstruível.

**Ações**
1. Defina a abrangência (código e regras · dados de projeto · estado operacional ·
   ambiente) e o que fica fora, com motivo [Livro p28].
2. Dê identidade única (ex.: `baseline-a05-001`) — nunca reutilize o identificador.
3. Preserve: histórico Git quando houver (um bundle **não** leva arquivos soltos,
   alterações não registradas, configuração local nem hooks) + cópia do que está
   fora do Git + banco SQLite pela **API de backup** (nunca copiar o arquivo em uso
   sem o `-wal`) + receita de recriação do ambiente; credenciais **não** entram
   [Livro p28–29; 3.0 R13.2].
   Ferramentas: `python <skill>/scripts/manifesto.py criar --raiz <origem> --saida <ref>/manifesto.json`;
   `python <skill>/scripts/backup_sqlite.py --origem <db> --destino <ref>/state.sqlite`;
   no kit: `python -m fundacao backup criar --destino <ref> --rotulo baseline-a05-001`.
4. Restaure em pasta **nova**, abra arquivos representativos e consulte o banco.
5. Prova negativa: altere um arquivo e remova outro **só na cópia de teste**; a
   comparação deve apontar ambos (`manifesto.py verificar`).

**Saídas:** manifesto, cópia recuperável, instrução de restauração, relatório.

**Critério:** restauração demonstrada (arquivos abrem, dados conferem, diferenças
provocadas detectadas); abrangência registrada só para o que foi ensaiado [Livro p30].

**Falhas:** arquivo existe mas não abre (placeholder de nuvem); caminho absoluto
na restauração; banco bloqueado (identifique o escritor, use backup); Git vazio
(preserve arquivos, registre ausência de histórico) [Livro p30]; origem do banco
inexistente → `backup_sqlite.py` recusa e não cria arquivo (confira o caminho).

## A5 — Núcleo e capacidades por etapas

**Entradas:** decisões (A3) e referência recuperável ensaiada (A4); matriz; trilha
essencial/avançada definida em A2.

**Ações**
1. **Núcleo mínimo [Livro A06 p32–35]:** identificação e validação de projeto, criação
   de tarefa, consulta de estado após reiniciar o processo, inventário fiel (planejado ·
   em desenvolvimento · bloqueado · implementado e ativo · implementado e inativo).
   Testes que importam: tarefa reaparece com mesmo id após reinício; outro projeto
   recebe negativa sem dados; configuração incompleta não deixa registro parcial
   (transação) [Livro p34].
2. Integre as capacidades nesta **ordem recomendada** (trilha essencial primeiro;
   ajuste à necessidade do projeto, mas mantenha todas na matriz):

| # | Capacidade | Referência | Requisitos |
|---|---|---|---|
| 1 | Núcleo, modelo de projeto, isolamento | `references/capacidades/11-manutencao-recuperacao.md` (A05), A6–A7 abaixo | R01–R04, R44 |
| 2 | Provedores e uso normalizado | `references/capacidades/03-provedores-modelos.md` | R12–R15 |
| 3 | Orquestração durável | `references/capacidades/01-orquestracao.md` | R05–R08 |
| 4 | Agentes e subagentes | `references/capacidades/02-agentes-subagentes.md` | R09–R11 |
| 5 | Componentes, skills, hooks/permissões, MCP, plugins | `references/capacidades/08-ferramentas-hooks-mcp-skills-plugins.md` + `references/seguranca-isolamento.md` | R32–R36, R52–R54 |
| 6 | Privacidade antes de dados reais | `references/privacidade-sigilo.md` | R55–R56 |
| 7 | Memória persistente | `references/capacidades/04-memoria.md` | R16–R20 |
| 8 | GOLD | `references/capacidades/05-gold.md` | R29–R31 |
| 9 | RAG e avaliação | `references/capacidades/06-rag.md` | R21–R25 |
| 10 | Consumo e qualidade | `references/capacidades/09-consumo-qualidade.md` | R37–R40 |
| 11 | Caches e CAG | `references/capacidades/07-cag-caches.md` | R26–R28 |
| 12 | Conversa, observabilidade, auditoria | `references/capacidades/10-observabilidade-conversa.md` | R41–R43, R49–R51, R57 |
| 13 | Atualização, desativação, restauração | `references/capacidades/11-manutencao-recuperacao.md` | R45–R48 |

3. Para **cada** capacidade: implementar → teste positivo → teste negativo → teste de
   recuperação (quando aplicável) → evidência → matriz → RETOMADA.

**Saídas:** código e configuração por capacidade; testes positivos e negativos;
`evidence/<capacidade>/`; linhas da matriz atualizadas; RETOMADA após cada capacidade.

**Critério:** cada capacidade da trilha escolhida tem evidência executada (positivo +
negativo) ou está `bloqueado` com bloqueio, impacto e condição de resolução; nenhuma
capacidade some da matriz; simulações rotuladas não promovem requisito de integração.

**Falhas:** dependência de acesso, hardware ou orçamento indisponível → código e testes
locais independentes avançam e o requisito fica `bloqueado`; teste negativo que passa
"por acaso" (dado não existia) → semeie marcador-canário e repita; capacidade que
quebra outra → volte à referência de A4 e registre a decisão.

## A6 — Modelo reutilizável de projeto [Livro A07 p36–39]

**Entradas:** núcleo funcionando (A5); convenções de nome e de pastas; componentes comuns.

**Ações**
1. `templates/project/` com **lista positiva** (instruções, configuração vazia,
   contrato de entregas, exemplo fictício). Nada de bancos, tokens, documentos de
   clientes, índices ou resultados anteriores.
2. Gerador `project create` com identificador estável (`project_id`), nome, finalidade,
   versão do modelo, componentes habilitados e locais próprios de dados e memória;
   valida colisão (maiúsculas, espaços, nomes reservados do Windows) antes de escrever.
3. Criação atômica: pasta temporária → validação → instalação; falha não deixa
   projeto parcial ativo.
4. Autorização por principal autenticado fora do modelo; contenção de caminhos;
   `project_id` no pedido não concede acesso.
5. Atualizar o modelo não migra instâncias: compare versão de origem, configuração
   atual e versão pretendida; migração é procedimento explícito [Livro p38].

**Saídas:** `templates/project/`; gerador; teste de criação, repetição e colisão.

**Critério:** repetição preserva o projeto existente; negativa entre projetos antes da
leitura; gerador não exige editar o núcleo para cada nome [Livro p38].

**Falhas:** colisão de nome ou nome reservado → recusar antes de escrever; falha no meio
da criação → nada fica ativo (a pasta temporária é descartada); modelo alterado depois
de criar projetos → registre a diferença (`projeto drift`) e trate a migração em C5/C6.

## A7 — Dois projetos distintos: reutilização e isolamento [Livro A07, A26, A36]

**Entradas:** modelo de projeto (A6); identidades de ensaio por projeto; marcadores-canário fictícios.

**Ações**
1. Crie ao menos dois projetos de domínios diferentes pelo mesmo modelo (padrão
   didático: `juridico-lab` e `reversa-lab`; aceite os domínios do usuário).
2. Coloque marcadores-canário fictícios em cada um (ex.: `JUR-SEGREDO-FIC`,
   `ENG-SEGREDO-FIC`) e execute a mesma operação comum nos dois.
3. Provas negativas pela **mesma função de leitura** usada pelo sistema: identidade
   de um projeto lendo o outro; `..` e link para fora da raiz; pedido com "sou
   administrador"; memória, busca, cache e componentes; sondagem de metadados
   (alheio responde igual a inexistente) [Livro p37–38, p77].
4. Reinicie o processo e confirme estado e isolamento. Crie um terceiro projeto
   (`pesquisa-lab`) sem copiar dados para provar reutilização [Livro p179].

**Saídas:** relatório de provas (positivas e negativas) com evidência por operação;
eventos de negativa na trilha; terceiro projeto criado vazio.

**Critério:** marcadores ausentes de saídas, contexto entregue ao modelo e logs;
negativas registradas com identidade, projeto e operação, sem conteúdo; nada revela
existência, nomes ou contagens do outro projeto.

**Falhas:** marcador aparece em qualquer saída → pare, registre como incidente,
corrija a camada que entregou o dado e repita todas as provas; volume sem permissões
do SO (exFAT/FAT) → isolamento só lógico, declarado como limitação antes de dados reais.

## A8 — Entrega, operação e retomada

**Entradas:** evidências de A1–A7; matriz; bloqueios conhecidos.

**Ações**
1. Monte `RELATORIO-FINAL.md` (esperado × observado, real × simulado), `EVIDENCIAS.md`
   por etapa e `GUIA-DE-OPERACAO.md` com os comandos reais usados.
2. Para cada bloqueio: impacto, condição de resolução e comando/prompt pronto para o
   ambiente adequado.
3. Valide a matriz (`matriz.py validar`) e a RETOMADA (`retomada.py validar`).
4. Gere as instruções da raiz [Decisão; 1.7.0]: `python <skill>/scripts/instrucoes_raiz.py gerar --raiz <raiz>`
   escreve o `AGENTS.md` (resumo gerado pela skill entre marcadores, mais um trecho do titular que ela preserva) e
   o `CLAUDE.md` com `@AGENTS.md`; `conferir --raiz <raiz>` aponta arquivo ausente, trecho gerado editado ou falta
   da importação. Sem eles, as regras da sessão só entram se a skill for acionada (capacidade 08 §6).

**Saídas:** `RELATORIO-FINAL.md`, `EVIDENCIAS.md`, `GUIA-DE-OPERACAO.md`, `AGENTS.md` e
`CLAUDE.md` na raiz, matriz validada e `RETOMADA.md` validada.

**Critério:** diga claramente o que foi **executado** e o que foi **validado**; nada de
"100% concluído" com integração ausente [Livro p181]; os estados (fundação implementada,
projeto criado, integração real com provedores, capacidade inativa) aparecem separados.

**Falhas:** matriz ou RETOMADA inválidas → corrija antes de encerrar; evidência citada
que não existe → retire a afirmação ou refaça a verificação; evidência ou histórico fora da
raiz, por ligação ou acima do teto → copie para `evidence/` e cite o caminho relativo [Decisão;
auditoria Codex Security da 1.7.6, #7]; evidência ou histórico em caminho protegido (`state/`,
`projects/<projeto>/data/`, segredo) → registre o resultado em `evidence/`, sem o dado [Decisão;
revisão de segurança da 1.7.7, R177-VAL-01]; sessão interrompida → a RETOMADA da última etapa
concluída é o ponto de continuidade.

---

## §Host — preparo da máquina para dados reais (Windows e WSL2)

**Quando:** antes de dados reais (itens 6, 7 e 11 de `assets/templates/CHECKLIST-DADOS-REAIS.md`), com o titular
presente, porque os dois scripts gravam na área dele e pedem senha de administrador. Origem: implantação real de
2026-10-20 (a âncora em cinco voltas, o perfil do WSL em três versões, perfis e hooks copiados à mão) [Decisão]. O
que cada um garante e por quê: `references/seguranca-isolamento.md` §5.

**Ordem** (cada passo confere antes o que já existe; repetir não duplica nada):
1. **Executor, só leitura:** roda os dois em simulação e entrega ao titular um cartão de parada
   (`references/comunicacao-leigo.md`) com os comandos abaixo prontos, já com os caminhos da máquina.
2. **Titular, no PowerShell comum do Windows** (sem "Executar como administrador"; o UAC aparece só para a âncora;
   aberto a partir de um terminal do PowerShell 7, o script descarta os caminhos de módulo do 7 [Decisão; 1.7.2]):
   ```
   powershell -ExecutionPolicy Bypass -File "<skill>/assets/host/windows/preparar-maquina.ps1" -Raiz "<raiz>" -Titular <id> -Projeto <projeto> -Backups "<pasta de backup em outro disco>"
   ```
   `-Projeto` também grava o projeto autenticado das sessões (`FUNDACAO_PROJECT`, que o `guarda_caminho.py` exige para
   liberar a escrita) no `settings.local.json` [Decisão; 1.7.0] e deixa nele só a identidade e o projeto, porque a
   sessão de dados reais carrega o arquivo inteiro; o anterior vai para `.claude/anteriores/` [Decisão; auditoria
   Codex Security da 1.7.6, #5]. Opcionais: `-NegarSkill nome1,nome2` (skills aninhadas em pastas de dados, listadas
   por `scripts/instrucoes_aninhadas.py`, negadas por nome nos dois perfis), `-SomenteLeitura "<pasta>"` (origem que a
   sessão só lê), `-Python <python.exe>` e `-TrocarChave` (troca de chave, com cópia da âncora anterior); `-Simular`
   ou `-WhatIf` só mostram o plano. Sem `-Python`, o interpretador sai das instalações registradas do Windows ou do
   PATH, nunca do `.claude/settings.json` existente; com ou sem ele, só roda o python.exe do instalador oficial
   (assinatura da Python Software Foundation), sem ligação no caminho e sem escrita para outras contas comuns;
   recusado, o script para com código 2 sem executar nada [Decisão; auditoria Codex Security da 1.7.6, #3]. Se a chave
   ainda não existir, o ssh-keygen pede a senha duas vezes: só o titular a digita e a anota fora do computador, junto
   com a impressão digital que o script mostra no fim.
3. **Titular, no terminal do Ubuntu** (o sudo pede a senha do Linux só para pacotes, AppArmor e `wsl.conf`):
   ```
   bash "<skill vista do WSL>/assets/host/wsl/preparar-wsl.sh" --raiz "<raiz vista do WSL>" --projeto <projeto> --titular <id> --claude-versao <versão> --claude-sha256 <hash do manifesto assinado>
   ```
   `--titular` é o mesmo `-Titular` do passo 2. O script só fixa no lançador o que confere inteiro: o perfil igual ao
   que o modelo da skill gera para a raiz (cada projeto da raiz, menos o da sessão, com escrita negada), os hooks
   iguais aos da skill e o `settings.local.json` só com a identidade de `--titular` e o projeto. Diferença: para
   (código 1) e aponta o passo 2; projeto criado depois dele também pede o passo 2 de novo [Decisão; auditoria Codex
   Security da 1.7.6, #5]. Sem o Claude Code no Ubuntu, o script para (código 3) e mostra o comando oficial de
   instalação; o login também é do titular. Depois, no PowerShell do Windows: `wsl --terminate <distribuição>`.
4. **Titular, no terminal do Ubuntu:** `bash ~/abrir-fundacao.sh` abre a sessão de dados reais (lançador gerado do
   modelo `assets/host/wsl/abrir-sessao.sh`, com o perfil `assets/host/wsl/settings.wsl.json` já preenchido). Ele
   confere pelo SHA-256 também o `settings.local.json` e o titular fixado no preparo: mudou depois, não abre; repita
   os passos 2 e 3.
5. **Executor:** repete as simulações (tudo "igual", âncora protegida e a impressão digital anotada pelo titular) e
   registra em `evidence/host/` o relatório do script do Windows, os SHA-256 e o que ficou pendente. Simulação nunca
   vale como execução real: sem a execução do titular, o passo fica pendente na RETOMADA.

**Códigos dos dois scripts:** 0 pronto e conferido (ou simulação sem erro) · 1 parou ou há conflito · 2 uso
incorreto (nada alterado) · 3 falta um passo do titular (no Windows, UAC recusado ou `-SemUAC`; no Ubuntu, instalar o
Claude Code e fazer o login). O hash oficial de cada versão do Claude Code está no manifesto assinado
(`references/fontes-verificadas.md` §1); sem `--claude-sha256`, o lançador fixa o binário atual, registrado como não
conferido.

---

## §Kit — comandos do kit de referência

```
python <skill>/scripts/instalar_kit.py --destino <raiz> [--simular]   # plano antes de escrever; conflito: nada escrito, código 3
python <skill>/scripts/instalar_kit.py --destino <raiz> --atualizar   # atualização C6: guarda a versão anterior
python <skill>/scripts/atualizar_fundacao.py checar --raiz <raiz>     # atualização C6 em um comando: só lê, sem executar a raiz
python <skill>/scripts/atualizar_fundacao.py aplicar --raiz <raiz> --backups <outro disco>  # backup, ensaio em cópias conferidas, promoção
python <skill>/scripts/atualizar_fundacao.py desfazer --registro <arq>  # volta o código; só registro ancorado em registry/atualizacoes.jsonl
# Códigos: 0 composição verificada · 3 incompleta (conflito; --manter-conflitos = estado misto registrado)
#          4 ligação/junção para fora do destino (nada escrito) · 5 falha na promoção (desfeita; com
#          `desfeito: false` o retorno também falhou: siga `erros` e `acao_necessaria`)
cd <raiz>
python -m fundacao init --admin <id-titular>      # estado, 1º administrador e registro de retiradas com identidade
# Identidade com dados reais: o lançador define FUNDACAO_PRINCIPAL antes da sessão (PowerShell: $env:FUNDACAO_PRINCIPAL="<id>").
# No laboratório (dados fictícios), use a identidade declarada pelo usuário e registre a origem (SKILL.md §7).
python -m fundacao projeto criar --id juridico-lab --nome "Laboratório jurídico" --finalidade "..."
python -m fundacao acl registrar --principal operador-juridico
python -m fundacao acl conceder --principal operador-juridico --recurso project:juridico-lab --acao-permitida read
python -m fundacao tarefa criar --projeto juridico-lab --objetivo "..." --chave aurora-001
python -m fundacao decisao preparar --projeto juridico-lab --tarefa <task_id> --entrega outputs/<arq> --tipo aceite --motivo "<palavras do titular>"
#   grava projects/<p>/decisoes/<id>.json; em para_o_titular, os comandos de assinar e conferir (--shell powershell|bash)
python -m fundacao decisao registrar --arquivo <decisão>    # confere a assinatura e registra; não confere = código 3
python -m fundacao tarefa concluir --decisao <aceite>       # só o aceite válido, registrado e mais recente conclui
python -m fundacao decisao conferir-ancora                  # sonda a âncora sem alterar; desprotegida = código 3
python -m fundacao status                          # recortado pela identidade
python -m fundacao componente listar | habilitar --id source_manifest
python -m fundacao eventos verificar
python -m fundacao eventos exportar --destino <raiz>/evidence/eventos.jsonl      # audit ou admin na fundação
python -m fundacao backup criar --destino <ref> --rotulo baseline-a05-001        # admin na fundação
python -m fundacao backup restaurar --origem <ref> --destino <nova-pasta> --retiradas <raiz>/state/retiradas.jsonl
#   autorizada pela fundação viva; com a origem danificada, pela cópia ancorada (livro ou --sha256-manifesto)
#   sem âncora: só com --aceitar-copia-sem-ancora "<motivo>" (fica na trilha); não liberada = código 3
#   `backup verificar` confere arquivos e banco (hash e contagens) contra o manifesto; não confere = código 3
#   cópia em pasta de rede (UNC) serve; restaure a fundação que será usada em disco local
python -m fundacao rota gasto --rota api_creditos  # gasto e tentativas sem custo medido (audit ou admin)
python -m fundacao rota custo --rota api_creditos --tentativa <event_id> --custo-usd 0.0123 --fonte "painel"
python -m fundacao.mcp_servidor --raiz <raiz>      # servidor MCP de leitura (stdio; requer o pacote mcp)
python <skill>/scripts/mcp_ensaio.py --raiz <raiz> --projeto <autorizado> --outro <nao-autorizado>
python -B -m unittest discover -s tests            # suíte de conformidade
# Os testes criam pastas temporárias. Para mantê-las dentro da raiz autorizada, antes defina
# TMPDIR=<raiz>/state/tmp-testes (crie a pasta; no PowerShell: $env:TMPDIR='<raiz>/state/tmp-testes').
# Windows: prefira raiz curta (ex.: D:/IA/fundacao). A pasta de trabalho de um processo não passa de
# 260 caracteres mesmo com caminhos longos ligados; cópias de ensaio em pastas fundas podem falhar.
```

Ferramenta própria que usa o kit direto (fora da CLI) abre o banco só se ele existir: `connect()` cria
um banco vazio, e com `state/` mascarado (sandbox) ou perdido o resultado parece sucesso [Decisão;
implantação real de 2026-10-20]. Siga a regra da CLI ("só o `init` cria o banco": confira
`state/state.sqlite` antes de abrir) e recuse a execução quando faltar.

Cobertura do kit: núcleo, projetos por modelo, ACL por identidade (comum/projeto/caso),
tarefas com checkpoints/retomada/decisão humana/orçamento, componentes com timeout
em subprocesso, memória versionada com promoção por hash, GOLD + RAG (FTS5 por
projeto), caches com invalidação, eventos encadeados, uso normalizado, seletor de
rota com tetos por rota e reconciliação de custo, adaptadores CLI isolados (prompt pela
entrada padrão e ambiente mínimo; código presente, não executado com provedor) e simulado
(rotulado), backup/restauração com registro protegido com identidade e reaplicação de
retiradas de fontes e de memória e de revogações, servidor MCP de leitura (ensaiado
localmente por stdio, com a versão de protocolo negociada registrada). Fora do kit (seguir
as referências de capacidade): registro do servidor MCP no host, hooks nativos
instalados no host, skills/plugins nos hosts, interface de conversa, painel, CAG com
modelo real (`scripts/cag_kv_demo.py`).
