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
- §Host Preparo da máquina e de cada projeto para dados reais (Windows e WSL2)
- §Kit Comandos do kit de referência

---

## A1 — Ambiente, instruções, recursos e fundação anterior [Livro A01 p8–11, A03 p16–19]

**Entradas:** pedido do usuário e escopo fixado (SKILL.md §1); pasta autorizada; `RETOMADA.md`/relatórios
anteriores (estado e evidências, não autorização); `AGENTS.md`/`CLAUDE.md`.

**Ações**
1. Inventário do ambiente, só se o pedido deixa sondar o host (SKILL.md §1, itens 1 e 3):
   `python <skill>/scripts/inspecionar_ambiente.py --pasta <raiz> --somente-localizar`. Não executa programas nem
   grava, mas lê PATH, algumas variáveis de ambiente, `/proc` e, no Windows, o registro; procura programas só nas
   pastas absolutas do PATH. Pedido restrito a uma pasta: não rode, e o ambiente fica "não medido" [achado R179-36;
   1.7.10]. Sem `--somente-localizar`, roda `--version` de CLIs (claude, codex, git…), `py -0p`/`pymanager list` e
   `wsl --list` (lista; não inicia WSL): só se o escopo permitir executar CLIs.
   `--saida <raiz>/evidence/ambiente/inventario-<data>.json` grava (exige escrita autorizada; recusa arquivo
   existente) [auditoria da 1.4.1, A18]. Nunca instala nem lê credenciais. Confira `pasta.sistema_de_arquivos`
   (exFAT/FAT = sem permissões do SO).
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

**Saídas:** `evidence/ambiente/inventario-<data>.json` (só com o inventário rodado e escrita autorizada),
`DIAGNOSTICO.md` (seções 1, 6, 7), `ACESSOS.json`, `ORCAMENTO.md`, `PERMISSOES.md` (leitura × gravação × ação externa;
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
   sem o `-wal`) + receita de recriação do ambiente; credenciais seguem o mecanismo
   próprio delas e não entram no pacote [Livro p28–29; 3.0 R13.2]. No kit não é assim
   [Decisão; 1.7.10]: o `backup criar` deixa fora o `.env`, mas leva como está, sem ler, o
   arquivo com cara de segredo, contado em `segredos_incluidos` (capacidade 11); o
   `manifesto.py criar` não lê nome de segredo (vai para `excluidos`).
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

## §Host — preparo da máquina e de cada projeto para dados reais (Windows e WSL2)

**Quando:** antes de dados reais (itens 6, 7 e 11 de `assets/templates/CHECKLIST-DADOS-REAIS.md` e o item C de
`assets/templates/CHECKLIST-PROJETO.md`), com o titular presente: os scripts gravam na área dele e pedem senha de
administrador (UAC no Windows, `sudo` no Ubuntu). Origem: implantação real de 2026-10-20 (a âncora em cinco voltas, o
perfil do WSL em três versões, perfis e hooks copiados à mão) e a 1.7.10 (perfil, lançador e área do titular por
projeto) [Decisão]. O que cada camada garante e até onde: `references/seguranca-isolamento.md` §5 e §8.

**Honestidade (registre sempre):** com a raiz em `/mnt/<letra>` (o disco do Windows visto do Ubuntu), o sandbox do
Claude Code não confinou os comandos nas sondas de 31/10/2026. Até o canário (passo 6) passar nessa forma de caminho,
o isolamento entre projetos no Ubuntu é lógico (perfil, hooks e porteiro), e nenhuma abertura vale sem a ficha
assinada e o canário aprovado.

**Forma fixa dos passos do titular** [Decisão; 1.7.10; revisão de segurança, CI-F1]: o titular copia cada comando dele
do modelo da skill instalada (a pasta da skill no perfil dele), nunca da cópia que a sessão preencheu; recusa comando
cujo programa fique dentro de `<raiz>/projects/`; e a sessão não muda estes passos. O cartão de parada só preenche os
valores (raiz, projeto, identidade, pastas).

**Ordem** (cada passo confere antes o que já existe; repetir não duplica nada). Os passos 2 a 5 voltam a cada projeto
novo; os passos 4 e 5, e o canário com o perfil novo, depois de cada atualização da fundação
(`references/fluxo-c-operar.md` C6).
1. **Executor, só leitura:** roda as simulações (`-Simular` nos scripts do Windows, `--simular` no do Ubuntu) e
   entrega ao titular um cartão de parada (`references/comunicacao-leigo.md`) com os comandos abaixo prontos, já com
   os caminhos da máquina. Nunca roda `wsl --shutdown` nem `--terminate`: fechar o Ubuntu é do titular, e com o
   Ubuntu ligado o executor para e pede.
2. **Titular, uma vez por projeto vindo de outra pasta (fluxo B), no terminal dele** (`python` no Windows, `python3`
   no Ubuntu): registra a origem.
   ```
   python <skill>/assets/host/preparo_host.py registrar-projeto --raiz "<raiz>" --projeto <projeto> --origem "<pasta da origem>"
   ```
   Grava `registry/projetos-host.json` (`fundacao.projetos_host/1`), que só o titular grava: os perfis negam às sessões
   a escrita nele. Opcionais, repetíveis: `--somente-leitura "<pasta>"` (outra pasta que o projeto só lê) e
   `--negar-skill <nome>` (skill aninhada que `scripts/instrucoes_aninhadas.py listar` achou na origem). A pasta tem
   de existir e ficar fora da raiz; o registro feito no Windows (`D:\...`) vale no Ubuntu (`/mnt/d/...`). O registro
   só cresce: não há comando para tirar uma pasta dele (pasta que mudou de lugar: registre a nova e apague a antiga
   da lista `origens` do projeto, à mão).
3. **Titular, no PowerShell comum do Windows, um projeto por vez** (sem "Executar como administrador"):
   ```
   powershell -ExecutionPolicy Bypass -File "<skill>/assets/host/windows/preparar-projeto.ps1" -Raiz "<raiz>" -Titular <id> -Projeto <projeto> -Backups "<pasta das cópias, em outro disco>"
   ```
   `-Backups` são as cópias de segurança (as mesmas regras do passo 4), repassadas ao preparo da máquina; com o disco
   delas desligado agora, `-BackupsAusente` com a mesma pasta (só a forma é conferida, e a negação vale quando o disco
   voltar); se ainda não há cópias, `-SemBackups` no lugar dele. Sem nenhum dos dois (ou com `-Backups` só de espaços),
   recusa com código 2 antes de gravar qualquer coisa, também na simulação, e mostra o comando pronto com `-Backups`;
   os dois juntos também recusam. Depois da primeira cópia (`registry/ultima-copia.json`, que o `backup criar` grava),
   o `-SemBackups` também recusa, e o comando pronto já traz a pasta das cópias: confira se é a sua (o registro só
   recusa e sugere, nunca aceita; uma sessão o forja). Lê o registro e roda o preparo da máquina (passo 4) com as
   origens e as pastas só de leitura de **todos** os projetos registrados e com as skills negadas de todos, somadas.
   Pasta registrada de outro projeto que
   sumiu (disco não montado) vira aviso e segue com o Edit negado; a do próprio projeto para o preparo dele (código 2).
   O `-Projeto` daqui é o da sessão do Ubuntu: o projeto das sessões do Windows não muda (para trocá-lo de propósito,
   `-ProjetoWindows <id>` com `-TrocarProjeto`). Recusa com o Ubuntu ligado (código 4): feche as janelas dele e, no
   PowerShell, rode `wsl --terminate <distribuição>`. No fim, mostra o comando do passo 5, já com os caminhos.
   `-AssinarFicha` assina a ficha de aberturas do projeto pela ferramenta fixa do titular (a cópia protegida, se
   instalada e conferida; senão, a da skill, que avisa na tela). É o último recurso: ele roda dentro do PowerShell
   deste script, que carrega o perfil do PowerShell, e uma sessão pode ter gravado esse perfil. A forma recomendada é a
   caixa Executar (Win+R), com o comando que o `abertura preparar` mostra (`references/fluxo-c-operar.md`, "Projetos
   no Ubuntu").
4. **Titular, no PowerShell comum: o preparo da máquina, por último no Windows**:
   ```
   powershell -ExecutionPolicy Bypass -File "<skill>/assets/host/windows/preparar-maquina.ps1" -Raiz "<raiz>" -Titular <id> -Projeto <projeto das sessões do Windows> -Backups "<pasta das cópias, em outro disco>"
   ```
   - **Um perfil só, refeito inteiro:** o perfil das sessões do Windows é um arquivo só
     (`<raiz>/.claude/settings.json`), e cada preparo o refaz inteiro, só com o que recebe. Por isso os dois scripts
     exigem `-Backups` ou, enquanto não há cópias, um `-SemBackups` explícito: sem nenhum dos dois, recusam com código 2
     antes de gravar qualquer coisa, com o comando pronto, e o do projeto (passo 3) repassa as cópias a este
     [Decisão; 1.7.10]. Rodado sozinho, este já nega a edição das origens e das pastas só de leitura de todos os
     projetos de `registry/projetos-host.json`, lidas pelo ajudante (caminho só do Ubuntu fica de fora);
     `-SomenteLeitura` fica para a pasta fora do registro. Rodado por último, ele fecha o Windows com o projeto das
     sessões do Windows e com o que só ele recebe (`-SomenteLeitura`, `-NegarSkill`): o que vier só pela linha de
     comando, fora de `registry/projetos-host.json`, vira pendência no relatório e na tela, porque o próximo preparo de
     um projeto (passo 3) refaz o perfil sem isso; para durar, registre a pasta ou a skill (passo 2). Com `-SemBackups`,
     o relatório deixa a pendência de rodá-lo de novo com `-Backups`; com uma cópia registrada em
     `registry/ultima-copia.json`, o `-SemBackups` recusa (código 2), e o comando pronto traz a pasta dela.
   - Calcula o plano inteiro antes da chave, do UAC e de qualquer gravação [Decisão; 1.7.10]. `-Projeto` é o projeto das
     sessões do Windows (o do coordenador), gravado no `env` do perfil; trocá-lo exige `-TrocarProjeto`, e sem a opção
     há conflito e nada é gravado. `-Backups` e `-SomenteLeitura` aceitam várias pastas, separadas por vírgula seguida
     de unidade (`"D:\a,E:\b"`); cada uma tem de existir, num disco local, fora da raiz e sem conter a raiz (a raiz de um
     disco só das cópias, `"F:\"`, vale como está). `-BackupsAusente` leva as cópias num disco desligado agora: a forma
     é conferida, a existência não, e elas saem negadas na leitura e na edição como as de `-Backups`.
   - Faz: a chave do titular (`~/.ssh/fundacao_titular`; se faltar, o `ssh-keygen` pede a senha duas vezes: só o
     titular a digita e a anota fora do computador, com a impressão digital que o script mostra no fim; chave que abre
     sem senha é recusada); a âncora das decisões (`C:\ProgramData\FundacaoIA\confianca\allowed_signers`, de dono
     Administradores), com a linha do titular nos namespaces `fundacao-decisao`, `fundacao-abertura` (a ficha de
     aberturas) e `fundacao-copia` (o livro de cópias assinado), pelo UAC; a linha da mesma chave sem um deles (a da
     1.7.9, só com o primeiro, ou a de uma 1.7.10 de antes, sem `fundacao-copia`) é trocada pela nova no mesmo UAC, com
     a mesma chave; no mesmo UAC, a cópia protegida da ferramenta do titular
     (`C:\ProgramData\FundacaoIA\ferramentas\<versão>`); os hooks da skill em `<raiz>/.claude/hooks` (também os do
     Ubuntu); o perfil das sessões do Windows e o `settings.local.json` só com a identidade. O perfil único do Ubuntu
     da 1.7.9 vai para `.claude/anteriores/`, como tudo o que o preparo troca.
   - A cópia protegida só registra um Python instalado para todos os usuários. Com o Python por usuário (em `AppData`),
     a forma do Windows de assinar a ficha fica pendente, com o motivo e sem UAC para ela, e vale a do Ubuntu (passo 5).
   - O Python que roda o ajudante e os hooks do Windows é o de `-Python` ou o das instalações registradas do Windows e
     do PATH, nunca o do perfil existente; só o python.exe do instalador oficial (assinatura da Python Software
     Foundation, pin em `assets/host/windows/pins-python.json`), sem ligação no caminho e sem escrita para outras
     contas comuns. Recusado, o script para com código 2 sem executar nada [Decisão; auditoria Codex Security da 1.7.6,
     #3].
   - Opcionais: `-NegarSkill nome1,nome2`, `-TrocarChave` (troca de chave, com cópia da âncora anterior), `-Simular` ou
     `-WhatIf` (só mostram o plano) e `-SemUAC` (a âncora e a cópia protegida ficam pendentes). Aberto a partir do
     PowerShell 7, o script descarta os caminhos de módulo do 7 [Decisão; 1.7.2].
5. **Titular, no terminal do Ubuntu, como o seu usuário, sem `sudo` na frente** (o script pede o `sudo` sozinho, só no
   que exige administrador; rodado como root, recusa com código 2). Antes, feche as sessões do Ubuntu e, no
   PowerShell, rode `wsl --terminate <distribuição>`; depois abra um terminal novo do Ubuntu só para o preparo, para
   nenhuma sessão rodar durante ele (o espelho em `<raiz>/.claude/projetos/` é gravado como root):
   ```
   bash "<skill vista do WSL>/assets/host/wsl/preparar-wsl.sh" --raiz "<raiz vista do WSL>" --projeto <projeto> --titular <id> --perfil-windows "/mnt/c/Users/<usuario>" --claude-versao <versão> --claude-sha256 <hash do manifesto assinado>
   ```
   `--titular` é o mesmo `-Titular` do Windows; `--projeto` se repete, um por projeto; `--perfil-windows` é a pasta do
   Windows do titular, que o perfil do projeto nega (o script a deduz quando a skill está em
   `/mnt/c/Users/<usuario>/...`). Opcionais: `--seccomp-versao <versão>` (o filtro seccomp do sandbox, decisão do
   titular; sem ele, o relatório diz "sockets sem filtro"), `--canario <relatório>` (passo 6) e `--simular`.
   - Na máquina ("igual" quando já feito): os pacotes que faltam (`bubblewrap`, `socat`, `python3-venv` e, sem o node,
     `nodejs` e `npm`), o perfil do AppArmor do `bwrap` quando o Ubuntu restringe namespaces, um só bloco `[interop]`
     desligado no `/etc/wsl.conf` (vale depois de reiniciar o Ubuntu: no PowerShell do Windows,
     `wsl --terminate <distribuição>`) e o Claude Code copiado para `~/.local/share/fundacao-ia/claude/<versão>/claude`,
     fora da limpeza automática de versões, e fixado pelo SHA-256 (sem o hash informado, o do binário atual, registrado
     como não conferido). O lançador único da 1.7.9 (`~/abrir-fundacao.sh`) é aposentado.
   - Para cada projeto, com `sudo` (`assets/host/preparo_host.py instalar-projeto`): a área do titular, de dono root,
     `/etc/fundacao-ia/projetos/<projeto>/` (o perfil gerado do modelo `assets/host/wsl/settings.wsl.json`,
     `porteiro.json`, `mcp.json`, `aberturas.json`, `ficha/`, `plugins/` e `hashes.json`), as cópias conferidas da
     skill e do Claude Code, o lançador `/usr/local/bin/abrir-fundacao-<projeto>` (do modelo
     `assets/host/wsl/abrir-sessao.sh`) e a cópia protegida da ferramenta do titular em
     `/usr/local/lib/fundacao-ia/<versão>/`, de dono root, de onde roda a forma do Ubuntu de assinar a ficha.
   - Só fixa o que conferiu inteiro: os hooks da raiz iguais aos da skill (por isso o Windows vem antes), o kit da raiz
     igual ao da skill (um `.pyc` solto, um `.git` ou um `.sqlite` em `fundacao/` recusam: rode antes a atualização,
     C6) e a ficha assinada da caixa de entrada. Sem o Claude Code no Ubuntu, para (código 3) e mostra o comando oficial
     de instalação. Projeto criado depois na raiz: o lançador dos outros recusa abrir até este passo rodar de novo.
6. **Titular, no terminal do Ubuntu: o canário** (`scripts/ensaio_isolamento_wsl.py`; passo a passo no item C de
   `assets/templates/CHECKLIST-PROJETO.md`). A IA não o roda. Depois do passo 5, que fixa o Claude Code, ele monta uma
   fundação fictícia numa pasta nova do mesmo disco da raiz, fora dela, e abre sessões curtas do Claude Code, que
   gastam a assinatura do titular: 12 com um barramento `/run/user/*/bus` no host, 11 sem. Vale só o relatório da forma
   de caminho da raiz (`drvfs:/mnt/<letra>` para a raiz no disco do Windows; o de `ext4` só serve com a raiz no ext4),
   com o mesmo Claude Code fixado (versão e SHA-256). Só com `conclusao.confina_comandos: true` (código 0), o titular o
   instala rodando de novo o passo 5 com `--canario <relatório>` (só o relatório que o ensaio da skill instalada gravou
   na casa dele, nunca um arquivo de `projects/`): o relatório vai para a área do titular, e só então a
   ficha de aberturas de um projeto é aplicada. Com `false` ou `null` (1.7.10.1), o mesmo passo instala o relatório
   como revogação: as aberturas ficam fechadas, salvo no projeto em que o titular assinar o aceite de risco desse
   relatório ([correção 1.7.10.1](atualizacao-1.7.10.1.md)); o isolamento continua lógico, e o resultado vai para o
   checklist e para a RETOMADA do projeto. O canário vem antes de
   qualquer dado real: se os comandos não ficarem confinados, a sessão de um projeto também pode gravar na pasta do
   Windows do titular, por `/mnt/c` (um atalho na pasta Inicializar, por exemplo), com efeito no próximo logon (risco
   deduzido das sondas, não medido).
   Refaça-o a cada perfil novo: o relatório instalado vale enquanto o Claude Code fixado e a forma de caminho forem os
   mesmos, sem conferir o perfil.
7. **Titular, no terminal do Ubuntu, como o seu usuário (sem `sudo`):** `abrir-fundacao-<projeto>` abre a sessão do
   projeto. O lançador confere pelo SHA-256 o que o preparo fixou. O que mudou desde então recusa: se a mudança foi do
   titular (uma atualização da fundação ou um projeto novo, por exemplo), rode de novo o passo 5; se não foi, não abra
   e avise o executor, como diz o lançador. Ele recusa também root, outro usuário, outra sessão do mesmo projeto, a
   interoperabilidade com o Windows ligada e a trava de manutenção; inicia o porteiro e abre o Claude Code na pasta do
   projeto. Na primeira sessão de cada projeto, o titular faz o `/login` (a configuração do Claude Code é por
   projeto). Feche antes as sessões do Windows que operam a fundação: o banco não abre pelos dois lados
   (`references/fluxo-c-operar.md`, "Projetos no Ubuntu").
8. **Executor:** repete as simulações (tudo "igual", a âncora protegida e a impressão digital anotada pelo titular) e
   registra em `evidence/host/` os relatórios dos scripts do Windows, os SHA-256 e o que ficou pendente.
   Simulação nunca vale como execução real: sem a execução do titular, o passo fica pendente na RETOMADA e no checklist
   do projeto.

**Códigos.** `preparar-maquina.ps1`: 0 pronto e conferido (ou simulação sem erro) · 1 parou ou há conflito · 2 uso
incorreto (nada alterado; também sem `-Backups` nem `-SemBackups`, ou com `-SemBackups` e uma cópia registrada, com o
comando pronto) · 3 tudo feito menos a âncora
ou a cópia protegida, que esperam o UAC (recusado, ou com `-SemUAC`). `preparar-projeto.ps1`: os mesmos, e 4 com o
Ubuntu ligado (nada alterado). `preparar-wsl.sh`: 0 pronto ·
1 parou (veja a linha `[erro]`) · 2 uso incorreto · 3 falta algo que só o titular faz (instalar o Claude Code, o `npm`
ou o `corepack`). O hash oficial de cada versão do Claude Code está no manifesto assinado
(`references/fontes-verificadas.md` §1).

---

## §Kit — comandos do kit de referência

```
python <skill>/scripts/instalar_kit.py --destino <raiz> [--simular]   # plano antes de escrever; conflito: nada escrito, código 3
python <skill>/scripts/instalar_kit.py --destino <raiz> --atualizar   # atualização C6: guarda a versão anterior
python <skill>/scripts/atualizar_fundacao.py checar --raiz <raiz>     # atualização C6 em um comando: só lê, sem executar a raiz
python <skill>/scripts/atualizar_fundacao.py aplicar --raiz <raiz> --backups <outro disco>  # backup, ensaio em cópias conferidas, promoção
#   1.7.10: recusa com o WSL ligado, trava a manutenção (state/manutencao.json) e amplia a política de backup (C6)
python <skill>/scripts/atualizar_fundacao.py desfazer --registro <arq>  # volta o código; só registro ancorado em registry/atualizacoes.jsonl
# Códigos: 0 composição verificada · 3 incompleta (conflito; --manter-conflitos = estado misto registrado)
#          4 ligação/junção para fora do destino (nada escrito) · 5 falha na promoção (desfeita; com
#          `desfeito: false` o retorno também falhou: siga `erros` e `acao_necessaria`)
# Os comandos abaixo rodam com a raiz como pasta atual, sem mudar a do shell (SKILL.md §1): ( cd <raiz> && ... )
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
python -m fundacao conhecimento listar --projeto <p>                # catálogo, pela autorização da fundação
python -m fundacao conhecimento buscar --projeto <p> --consulta "..."  # trechos aprovados; negativa = access_denied
python -m fundacao componente listar | habilitar --id source_manifest
python -m fundacao eventos verificar
python -m fundacao eventos exportar --destino <raiz>/evidence/eventos.jsonl      # audit ou admin na fundação
python -m fundacao backup criar --destino <ref> --rotulo baseline-a05-001        # admin na fundação
python -m fundacao backup situacao              # idade da última cópia; com mais de 7 dias, o comando da próxima (C9)
python -m fundacao banco situacao               # a trava do banco (state/banco.trava), sem abrir o banco nem exigir identidade
python -m fundacao banco destravar --confirmar  # só o titular: tira o marcador velho do outro lado; recusa o vivo
python -m fundacao abertura vigente --projeto <p> --json   # a ficha de aberturas em vigor, sem banco nem identidade
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
