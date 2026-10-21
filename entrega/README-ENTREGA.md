# Entrega — skill `fundacao-ia-multiprojetos`

> **Cópia pública (19/10/2026).** Este repositório é uma cópia saneada do projeto: a pasta `auditoria/`
> (relatórios de auditoria, inclusive os recebidos de terceiros, e as respostas) e o workspace de desenvolvimento
> (`fundacao-ia-multiprojetos-workspace/`: iterações, cópias congeladas, sondas e registros) ficaram de fora, por
> decisão do titular; nos textos, o nome de usuário, a máquina e os caminhos locais foram substituídos por
> `<usuario>`, `<maquina>`, `<raiz-do-projeto>` e `<pasta-de-desenvolvimento>`. Os pacotes (`dist/`,
> `transferencia/`) são os originais, byte a byte. As citações a `auditoria/…` e ao workspace neste README
> referem-se a arquivos que só existem no projeto original.

Data: 18–21/10/2026 · Versão da skill: **1.7.3** (kit de referência 1.7.2) · Licença: **MIT** desde a 1.4.3 ·
Ambiente de criação e teste: Windows 11, Python 3.12.10, SQLite 3.49.1 (FTS5), Claude Code 2.1.302 (registrado em 18/10).

> **1.7.3 (21/10/2026):** a CI pública da 1.7.2, a primeira a rodar as quatro verificações até o fim nas dez rodadas,
> falhou em três pontos de ambiente que este computador não reproduz; a 1.7.2 foi publicada, instalada e aplicada à
> fundação, mas não declarada liberada. (1) O instalador recusava o `atualizar` depois de uma troca interrompida com a
> marca ilegível quando o perfil tem nome curto (`RUNNER~1` no Windows do GitHub): a ligação pendurada devolvia o alvo
> como foi gravado, e a cópia esperada saía pelo nome longo. Agora o alvo gravado passa pelo caminho final antes da
> comparação; um teste novo abre o perfil por uma junção, que reproduz o efeito aqui. (2) O CEN-11 lia o cabeçalho do
> `SKILL.md` com o PyYAML, que só existe neste computador: sem ele, o cenário fica BLOQUEADO, como o CEN-10 e o
> CEN-15, e as verificações que não dependem do pacote rodam. (3) O teste da sondagem da âncora esperava o usuário
> como dono do arquivo novo; no Windows Server elevado da CI o dono é o grupo Administradores, e o teste passa a
> seguir o dono real. A revisão de segurança independente achou um problema introduzido pela correção (2) (VCT170-06,
> baixo): com a opção da CI, um cenário bloqueado em parte perdoava também uma verificação que rodou e falhou; agora o
> bloqueio só perdoa o que não rodou, e o CEN-11 confere, sem o PyYAML, que o cabeçalho existe. Kit inalterado
> (1.7.2). Resultados: Windows deste PC — kit 326 OK (5 pulados), scripts 184 OK (2 pulados), entrega 96 OK (2
> pulados), cenários 16/16 (112/112); Ubuntu do WSL — scripts 184 OK, entrega 96 OK, cenários no modo da CI com CEN-10
> e CEN-15 bloqueados e os demais aprovados; 342 referências e 0 ausentes.

> **1.7.2 (21/10/2026; publicada, instalada e aplicada, com a CI pública vermelha):** a CI pública, conferida pela primeira vez na liberação da 1.7.1, falhou nas 10 rodadas por
> diferenças de ambiente em testes que só tinham rodado neste computador; a 1.7.1 foi publicada, instalada e aplicada
> à fundação, mas não declarada liberada. Correções: no Windows do GitHub, o runner é administrador e o
> `preparar-maquina.ps1` recusa rodar elevado (por desenho) — os ensaios com a conta comum são pulados num processo
> elevado e um teste novo confere a recusa; o Windows PowerShell aberto a partir do PowerShell 7 não carregava o
> `Get-Acl` — o script descarta os caminhos de módulo do 7 (vale também para o titular que abrir pelo pwsh); os testes
> do preparo usam o caminho longo da pasta temporária; no Linux, testes que supunham o Windows (decisões, perfil,
> lançador sem bit de execução) e o teste que perguntava por `/root/.bashrc`. Os cenários que dependem de pacotes
> opcionais (CEN-10, `torch`; CEN-15, `mcp`) ficam BLOQUEADOS onde eles faltam — nunca aprovados — e só a CI pública
> deixa o bloqueio não reprovar; a CI passa a mostrar todas as falhas de uma vez. Kit 1.7.2 (um teste do kit mudou).
> Resultados: Windows deste PC — kit 326 OK (5 pulados), scripts 184 OK (2 pulados: um é a recusa elevada, que só roda
> como administrador), entrega 92 OK (2 pulados); Ubuntu do WSL — kit 326 OK, scripts 184 OK, entrega 92 OK, CEN-10 e
> CEN-15 bloqueados; cenários neste PC 16/16 (111/111); 342 referências e 0 ausentes.

> **1.7.1 (21/10/2026; publicada, instalada e aplicada, com a CI pública vermelha):** correção achada pelo próprio ciclo de liberação. A 1.7.0 foi empacotada (`593a7f01…`), mas a
> montagem da transferência a recusou: a varredura de segredos leu como token atribuído o valor fictício de um exemplo
> de configuração do Codex num teste do inventário do host (falso positivo, da mesma classe do que parou a 1.6.0). A
> variável fictícia mudou de nome, e um teste novo aplica os padrões da varredura a todo o pacote (o da 1.6.1 cobria só
> o preparo do host). A 1.7.0 não foi instalada nem publicada; a 1.7.1 é a 1.7.0 com essa correção (kit 1.7.0, sem
> mudança) e com a revisão de segurança estendida até ela. Resultados: kit 326 OK (5 pulados); scripts 182 OK (1
> pulado); entrega 89 OK (2 pulados); ferramentas de liberação 28 OK; cenários 16/16 (111/111); 342 referências e 0
> ausentes; 66 comandos citados conferidos.

> **1.7.0 (21/10/2026, empacotada e recusada na transferência; não instalada nem publicada):** as quinze melhorias da análise do vibe-coding-toolkit (MIT, 21/10/2026), aprovadas pelo
> titular na conversa ("1.c / O resto adotar as recomendações"):
> - **Instruções na raiz:** `scripts/instrucoes_raiz.py` gera o `AGENTS.md` (resumo da skill entre marcadores, sem
>   nomes de projetos, com um trecho do titular que a skill preserva) e o `CLAUDE.md` com `@AGENTS.md`; as sessões
>   abertas na raiz passam a ler as regras sem acionar a skill. O `atualizar_fundacao.py aplicar` as regenera (guarda as
>   anteriores; o `desfazer` devolve), e o backup do kit sempre as leva. AGENTS.md escrito à mão não é sobrescrito.
> - **Pastas de dados não viram instrução:** os perfis do host excluem `projects/*/data/` das instruções
>   (`claudeMdExcludes`); `scripts/instrucoes_aninhadas.py` lista instruções e skills aninhadas, que o
>   `preparar-maquina.ps1 -NegarSkill` nega por nome. **Sessão de dados reais sem web:** o perfil do WSL nega
>   `WebFetch` e `WebSearch` (item 12 do checklist). **Projeto autenticado no lançador:** `-Projeto` grava
>   `FUNDACAO_PROJECT`, que o `guarda_caminho.py` exige.
> - **Rotas:** a política é validada ao carregar (tipo errado, rota inexistente e chave desconhecida recusam), e o
>   desvio local da rota sigilosa só vale ligado a uma decisão registrada (`registry/configuracao-decidida.json`;
>   antes, o teste era pulado na raiz implantada).
> - **Catraca de testes:** na atualização da fundação, teste que some ou passa a ser pulado é regressão, salvo retirada
>   declarada no kit novo; enfraquecer teste deixa de ser decisão de rotina (SKILL.md §4). **Órfãos:** arquivo que o kit
>   anterior instalou e o novo não tem sai da raiz guardado no backup e volta no `desfazer`.
> - **CI pública** no GitHub (workflow `validar`: as cinco verificações em Windows e Ubuntu, cinco rodadas, ações
>   fixadas por SHA, só leitura). **Também:** RETOMADA enxuta, com histórico arquivado e conferido; comandos citados nas
>   referências conferidos contra o código; canários nos caminhos de falha; fronteiras do código e teto de tamanho como
>   teste; avaliações E10–E12; modelo de revisão de segurança por versão; regra de ondas para agentes em paralelo; e o
>   inventário do ecossistema do host (`scripts/inventariar_host.py`), conferido na atualização.
> - A simulação da CI numa cópia saneada achou dois testes com a identidade real e um e-mail escrito por extenso, que a
>   cópia pública recusaria; corrigidos antes do pacote.
> - **Revisão de segurança independente** (outro contexto, somente leitura) da diferença 1.6.1..1.7.0: três achados
>   médios introduzidos nesta versão, corrigidos antes do pacote, cada um com o cenário de falha virado teste — caminho
>   forjado no registro de instalação fazia a atualização retirar o `.claude/settings.json` como "órfão" (VCT170-01);
>   registro forjado fazia o `desfazer` apagar fora da raiz ou sobrescrever `.claude/` (VCT170-02); o inventário do
>   host gravava o caminho do projeto dos plugins e os argumentos de um `command` MCP em texto único (VCT170-03). A
>   segunda passagem achou a variante com junção dentro da raiz (`tests/elo` → `.claude`), que passava pela conferência
>   de texto (VCT170-04): agora cada componente do caminho é conferido sem seguir ligação. E uma trava nova: o lançador
>   do WSL não abre se o `settings.local.json` entregar outro projeto.
>
> Resultados, em cópias, pastas e perfis descartáveis: kit 326 OK (5 pulados); scripts 181 OK (1 pulado); entrega 89
> OK (2 pulados); ferramentas de liberação 28 OK; cenários 16/16 (111/111); 341 referências e 0 ausentes; 66 comandos
> citados conferidos; revisão de segurança independente da diferença 1.6.1..1.7.0 em `entrega/auditoria/` (cópia
> privada). Kit 1.7.0. Liberada pelo `liberar.py`, que nesta versão passa a exigir essa revisão, a varrer antes os
> resíduos da cópia pública, a aplicar a catraca contra a versão anterior e a conferir a CI do commit publicado; o
> resultado fica em `outputs/liberacao/1.7.0/LIBERACAO.json` do projeto fundacao-de-ia.

> **1.6.1 (21/10/2026):** correção achada pelo próprio ciclo de liberação. Na 1.6.0, a montagem da transferência
> recusou o pacote: a varredura de segredos leu como credencial atribuída o campo com o estado da senha da chave no
> relatório do `preparar-maquina.ps1` (falso positivo). O campo passou a se chamar `estado_da_senha`, com uma regressão
> que usa o mesmo padrão da varredura. Na conferência antecipada do saneamento da cópia pública, exemplos e valores de
> teste com dados desta máquina (a raiz, o usuário e caminhos do perfil), que o saneamento trocaria ou recusaria,
> viraram valores fictícios nos scripts e nos testes do host e nos testes das decisões do kit. A 1.6.0 foi empacotada
> (`eae5f9d2…`), mas não foi instalada nem publicada. Kit 1.6.1, porque testes do kit mudaram.
> Resultados, em cópias, pastas e perfis descartáveis: kit 301 OK (5 pulados); scripts 135 OK (1 pulado); entrega 81
> OK (2 pulados); ferramentas de liberação 17 OK; cenários 16/16 (111/111); 312 referências e 0 ausentes; saneamento da
> cópia pública conferido antes da publicação (0 resíduos nos arquivos mudados desde a 1.5.1).
> Pacote `.skill` `ac69a9c4…8795` (158 arquivos). **Instalada no perfil em 21/10/2026, às 02h28** (`atualizar --sha256`;
> a 1.5.1 ficou em `~/.agents/skills-anteriores/`, conferida contra o pacote dela). Na mesma liberação, pela skill
> instalada, a fundação deste computador passa para o kit 1.6.1 (backup antes e depois, ensaio numa cópia restaurada)
> e a cópia pública vai ao GitHub; o resultado fica em `outputs/liberacao/1.6.1/LIBERACAO.json` do projeto
> fundacao-de-ia. Registros: `fundacao-ia-multiprojetos-workspace/correcoes-1.6.1/`.

> **1.6.0 (21/10/2026):** duas automações pedidas pela auditoria da implantação real deste computador (66 intervenções
> do titular, 10 por lacunas da skill), feitas por duas sessões na mesma árvore e liberadas juntas:
> - **Barreira de decisões assinadas no kit (kit 1.6.0):** a barreira da DECISAO-003 da fundação de referência passa a
>   ser do kit (`fundacao/core/decisoes.py`). Aceite, pedido de correção e rejeição de uma entrega viram JSON canônico
>   com o SHA-256 da entrega exata, assinado com `ssh-keygen -Y` no namespace `fundacao-decisao` e conferido contra a
>   âncora `allowed_signers`, que só o administrador altera; o `ssh-keygen` é o do sistema, por caminho fixo. CLI
>   `python -m fundacao decisao preparar|verificar|registrar|conferir-ancora|comando` e `tarefa concluir --decisao`
>   (o kit só tinha criar e ver); recusa = código 3; o comando do titular sai no shell certo (PowerShell ou bash do
>   WSL); política `registry/politica-decisoes.json`, com a âncora padrão como piso; a sondagem da âncora confere
>   também as pastas acima e as ligações no caminho. Compatível com as 8 decisões já registradas na fundação deste
>   computador (conferido só lendo).
> - **Preparo do host em scripts versionados (`assets/host/`):** os passos manuais que mais custaram (a âncora em cinco
>   voltas de ACL, três versões do perfil do WSL, perfis e hooks copiados à mão) viraram dois scripts que o titular roda
>   no próprio terminal, com simulação antes. `windows/preparar-maquina.ps1`, no PowerShell comum: chave do titular
>   pelo `ssh-keygen` do sistema (a senha é digitada só por ele; chave sem senha é recusada); âncora com dono
>   Administradores, herança cortada e arquivo herdando da pasta, com o UAC só nessa etapa e a conferência pela conta
>   comum, sem alterar nada; hooks e perfis (`settings.json`, `settings.wsl.json`, `settings.local.json`) gerados pelos
>   modelos em `<raiz>/.claude`, com cópia do que trocar; `-Simular`/`-WhatIf`, `-SemUAC` e relatório JSON.
>   `wsl/preparar-wsl.sh`, no Ubuntu: `bubblewrap` e `socat` (e o perfil do AppArmor do `bwrap` quando preciso), um só
>   bloco `[interop]` desligado no `/etc/wsl.conf`, o Claude Code copiado e fixado por SHA-256 e o lançador
>   `wsl/abrir-sessao.sh`, que confere binário, perfil e hooks pelo hash e abre com o prompt de retomada; `sudo` só em
>   pacotes, AppArmor e `wsl.conf`. O perfil do WSL sai igual, em conteúdo, ao v3 provado no caso real (`state/` em
>   `allowRead` e `allowWrite`). Conferência só de leitura nesta máquina: chave e âncora iguais e protegidas, hooks
>   iguais; o `settings.json` ganharia `Read(~/.ssh/**)`, e o `settings.wsl.json` só muda a ordem dos projetos negados.
> - O README público da 1.5.1 apontava os cenários para `RESULTADOS-versao-1.5.1.md`, que não chegou a ser gravado; a
>   1.6.0 grava `avaliacoes/cenarios/RESULTADOS-versao-1.6.0.md`.
>
> Resultados, em cópias, pastas e perfis descartáveis: kit 301 OK (5 pulados); scripts 134 OK (1 pulado; 66 novos do
> preparo do host, num PowerShell e num bash do Git de verdade); entrega 81 OK (2 pulados); ferramentas de liberação 17
> OK; cenários 16/16 (111/111); 312 referências e 0 ausentes. Não executados aqui: o UAC e o `sudo` reais e o WSL de
> verdade, que ficam com o titular (seção 9). Autorização: o pedido do titular na conversa de 2026-10-20 (DECISAO-004 da
> fundação); nesta rodada ele iniciou as duas sessões pelos cartões de melhoria propostos, sem texto novo.

> **1.5.1 (20/10/2026):** correção achada pelo próprio ciclo de liberação. Na 1.5.0, o `atualizar_fundacao.py` (pela
> 1.5.0 já instalada) ensaiou o kit novo numa cópia restaurada da fundação deste computador e **recusou promovê-lo**:
> `test_backup_completo` lia a política de backup local da raiz implantada (`registry/backup_policy.json`) em vez de
> conferir a padrão — falha que só aparece numa fundação real. A raiz não foi alterada; ficaram o backup ANTES e o
> registro da falha. Correções, cada uma com regressão que falha na 1.5.0 e passa na 1.5.1:
> - o teste isola a política local; `scripts/tests/test_conformidade_configuracao_local.py` cobre rota e backup
>   numa raiz implantada com configuração própria;
> - o ensaio apaga a cópia de ensaio também na falha, porque ela tem os dados da fundação (`--manter-ensaio` para
>   examinar), e o registro guarda o motivo de cada teste que falhou;
> - (ferramenta privada) o `liberar.py` usa no README público o hash da última versão publicada.
>
> Kit 1.5.1 (um teste do kit mudou). Resultados, em cópias e perfis descartáveis: kit 238 OK (4 pulados); scripts
> 63 OK (1 pulado); entrega 81 OK (2 pulados); ferramentas de liberação 16 OK; cenários 16/16 (111/111); 285
> referências e 0 ausentes; pacote `.skill` `cf1c9758…d7e6` (139 arquivos). **Instalada no perfil em 20/10/2026, às 23h48**
> (`atualizar --sha256`; a 1.5.0 ficou em `~/.agents/skills-anteriores/`), a fundação deste computador atualizada
> para o kit 1.5.1 com backup antes e depois e ensaio numa cópia restaurada, e a cópia pública enviada ao GitHub (a
> primeira publicada desde a 1.4.5). Autorização: pedido do titular na conversa (DECISAO-004 da fundação). Registros:
> `fundacao-ia-multiprojetos-workspace/correcoes-1.5.1/`.

> **1.5.0 (20/10/2026):** resposta a **duas auditorias externas** recebidas em 20/10 — a auditoria técnica sobre a 1.4.1
> (A01–A19, com patch proposto) e a varredura de segurança da cópia pública 1.4.5 (#1–#25) — e **automação para quem
> não é da área técnica**, a partir da auditoria da implantação real neste computador (66 intervenções do titular em
> ~23 h, 19 evitáveis e 10 causadas por lacunas da skill). Verificação item a item em
> `auditoria/VERIFICACAO-AUDITORIAS-2026-10-20.md`: os 44 achados procedem (A01 parcial; #4 é limite de arquitetura,
> documentado); cada correção de código tem regressão que falha na 1.4.5 e passa na 1.5.0. O patch do auditor parte da
> 1.4.1 e não foi aplicado: serviu de referência.
> - **Instalador e empacotador:** `--sha256` obrigatório em `instalar`/`atualizar` (o `SHA256SUMS.txt` ao lado só
>   detecta corrupção); pacote lido uma vez, com hash e extração dos mesmos bytes; entradas conferidas antes de extrair;
>   falha dupla de troca e retorno relatada com os caminhos; `empacotar.py` recusa ligações; `instalar_kit.py` não
>   declara desfeito quando o retorno falha.
> - **Kit 1.5.0:** saída conferida por hash e posse por geração na orquestração; prazo persistido; árvore de processos
>   encerrada no timeout; descoberta sem importar o pacote pai; custo como Decimal finito; rota Codex só com
>   `isolamento_leitura`; revisões de cache no alcance certo, aprovação revalidada, arestas autorizadas, versões ≥ 1,
>   fonte presa ao escopo, promoção legada falha fechada e reconferência de permissão dentro das transações; backup
>   sem seguir ligações, com âncora externa (`sha256_manifesto` e `state/copias.jsonl`) e **completo** (registros da
>   fundação, lista em `registry/backup_policy.json`). Sem migração de esquema (`user_version` 4).
> - **Scripts:** manifesto sem seguir ligações e sem descrever a si mesmo; `backup_sqlite.py` no mesmo snapshot;
>   `caracterizar.py` guarda a saída parcial; `inspecionar_ambiente.py` com efeitos declarados; `retomada.py` declara a
>   validação estrutural; hook de caminho nega raiz redirecionada e ligações; **`atualizar_fundacao.py`** (novo):
>   atualização da fundação em um comando, com backup antes, ensaio numa cópia restaurada, promoção, backup depois e
>   `desfazer`.
> - **Instruções:** escopo antes da retomada; RETOMADA é índice, não autorização; checklist com objetivos por host;
>   MCP com hashes; **`references/comunicacao-leigo.md`**, formulário único de implantação, folha de decisões, fluxo B
>   com dois portões e ritmo sem "posso seguir?".
> - **Avaliações:** verificador lê o banco como dado; acesso classificado pela estrutura do comando; componente legado
>   conferido por manifesto; fixture com `case_id` contido; CEN-11 encontra o `quick_validate` do plugin oficial.
>
> Resultados na 1.5.0, em cópias e perfis descartáveis (Windows 11, Python 3.12.10): kit 238 OK (4 pulados, link simbólico sem privilégio); scripts
> 62 OK (1 pulado); entrega 81 OK (2 pulados); ferramentas de liberação 16 OK; cenários 16/16 (111/111 verificações); 285 referências e
> 0 ausentes; pacote `.skill` `69ffe53c…f39f` (139 arquivos). Pelo `liberar.py` (ferramenta privada do projeto, que
> só declara a versão liberada depois de conferir GitHub, perfil e fundação), a **1.5.0 foi instalada no perfil em
> 20/10/2026, às 23h22** (`atualizar --sha256`; registro em `ambiente/instalacao-2026-10-18.json`). A etapa seguinte,
> a atualização da fundação deste computador, **recusou promover o kit 1.5.0**: o ensaio numa cópia restaurada achou
> uma regressão (ver 1.5.1). A fundação não foi alterada e a 1.5.0 **não foi publicada**. Autorização: pedido do
> titular na conversa (DECISAO-004 da fundação). Registros: `fundacao-ia-multiprojetos-workspace/correcoes-1.5.0/`.

> **1.4.5 (19/10/2026):** fecha as pendências da conferência da 1.4.3 que a 1.4.4 deixou, a pedido do titular:
> - **CF-05 (redação)** o bloco 1.4.2 deste README deixa de chamar a troca de "atômica" e remete à descrição da 1.4.3;
>   o R46 do gerador de rastreabilidade (e, por ele, `MATRIZ-RASTREABILIDADE.md/.csv` e `references/requisitos.md`,
>   que vai dentro da skill — daí a versão nova) descreve a atualização da skill "por renomeação, com retorno"; a matriz
>   de hosts identifica a versão do plugin oficial do skill-creator que estava ativa (`ea10b213686c` até 20h08 de
>   19/10, `a0b04d9ddcca` desde então, mesmo `quick_validate.py`);
> - **CF-06b** o `.gitattributes` da cópia pública guarda `entrega/leitura/logs/*.log` byte a byte (`-text`): o
>   `b2s_extract_text.log` volta a ter CRLF no remoto, como o arquivo saneado; a parte (a) já estava resolvida na 1.4.4;
> - **versão do kit** mantida em **1.4.1**, por decisão do titular (nenhum arquivo do kit mudou); a regra está na seção 5.
>
> Nada mais mudou na skill além de `requisitos.md` (R46) e da versão. Resultados na 1.4.5, em cópias e perfis
> descartáveis: kit 166 OK (3 pulados), scripts 23, entrega 40, cenários 16/16 (111/111), 258 referências e 0 ausentes
> na árvore (257/0 + 1 fora no pacote), `quick_validate` válido na árvore e no pacote; pacote `.skill` `1134a4f1…1ac9`
> (123 arquivos) e completo `5a601327…d3ad` (146), iguais à árvore, com as suítes do kit e dos scripts rodadas a partir
> do pacote (166 OK e 3 pulados; 23 OK); transferência `fundacao-ia-multiprojetos-1.4.5.zip` (`93548ea7…e4e1`). A
> **1.4.5 foi instalada no perfil em 19/10/2026, às 22h16** (`atualizar --sha256`; 123 arquivos, 0 divergências); a
> 1.4.4 ficou em `~/.agents/skills-anteriores/` e confere com o pacote dela. Cópia pública sincronizada e enviada ao
> repositório público. Registros: `fundacao-ia-multiprojetos-workspace/correcoes-1.4.5/`.

> **1.4.4 (19/10/2026):** resposta à **conferência independente da 1.4.3** (`auditoria/CONFERENCIA-1.4.3.md`, sessão
> independente — Fable 5.1 —, só leitura, em cópias e perfis descartáveis: APROVADA COM RESSALVAS; as nove correções
> AF-01 a AF-09 e todos os números da 1.4.3 confirmados; um achado P2 e cinco P3). CF-01 a CF-04 corrigidos, cada um
> com regressão que falha na 1.4.3 e passa na 1.4.4 (`testes/test_conferencia_1_4_3.py`, 6 testes, e uma verificação
> nova no CEN-13):
> - **CF-01 (P2)** o `guarda_identidade.py` volta a negar as formas explícitas de atribuição no PowerShell que a
>   correção AF-07 havia deixado passar — caminho `env:` entre aspas, `-Path:`/`-Path=`, `Env:\`, `Remove-Item`
>   entre aspas, `+=` — e passa a negar também `New-Item -Path env: -Name` e parâmetro com valor antes de `-Path`;
>   leitura e comparação (`echo`, `Get-ChildItem`, `-eq`, `==`) seguem livres (50 comandos conferidos em memória:
>   0 divergências, contra 15 do padrão da 1.4.3);
> - **CF-02** `remover --confirmar` remove (só a ligação) e relata uma ligação pendurada com o nome desta skill, em vez
>   de mantê-la com código 1; a ligação para a pasta de outra skill continua mantida (AF-04);
> - **CF-03** o instalador lê o `SKILL.md` da origem em UTF-8 com BOM e, sem `name` legível, diz isso na recusa, em
>   vez de "declara name None";
> - **CF-04** com a marca de troca ilegível, as cópias preparadas que sobram em `~/.agents/skills-preparo/` são
>   removidas e relatadas em `passos`, em vez de ficarem órfãs.
>
> O kit não mudou (1.4.1). CF-05 (redação) e a parte (b) do CF-06 (fim de linha de um log no remoto) ficam para a
> próxima rodada; a parte (a) do CF-06 foi resolvida: o bloco "Cópia pública" do README da cópia pública passou a ser
> produzido pelo montador. Resultados na 1.4.4, em cópias e perfis descartáveis: kit 166 OK (3 pulados), scripts 23,
> entrega 40, cenários 16/16 (111/111), 258 referências e 0 ausentes na árvore (257/0 + 1 fora no pacote),
> `quick_validate` válido (validador do aplicativo e do plugin oficial, na árvore e no pacote extraído), 146 arquivos
> na árvore; pacote `.skill` `b54b1714…401c` (123 arquivos) e completo `2ffbf1d2…1a10` (146), iguais à árvore, com
> as suítes do kit e dos scripts rodadas a partir do pacote (166 OK e 3 pulados; 23 OK); transferência
> `fundacao-ia-multiprojetos-1.4.4.zip` (`387ce8b2…408e`). A pedido do titular, a **1.4.4 foi instalada no perfil em
> 19/10/2026, às 21h36** (`atualizar --sha256`, hash conferido antes de extrair; 123 arquivos, 0 divergências); a 1.4.3
> ficou em `~/.agents/skills-anteriores/` e confere com o pacote dela. A cópia pública foi sincronizada e enviada ao
> repositório público. Registros: `fundacao-ia-multiprojetos-workspace/correcoes-1.4.4/` (snapshot da 1.4.3,
> regressões vermelhas e verdes, suítes, cenários, tabela do padrão do hook, empacotamento, transferência, instalação
> e sincronização).

> **1.4.3 (19/10/2026):** resposta à **auditoria final da 1.4.2** (`auditoria/AUDITORIA-FINAL-1.4.2.md`, sessão
> independente — Fable 5.1 —, só leitura, em cópias e perfis descartáveis: APROVADA COM RESSALVAS, dez achados P3,
> nenhum P1 ou P2; todos os números declarados para a 1.4.2 reproduzidos). Mudanças, cada uma com regressão que
> falha na 1.4.2 e passa na 1.4.3 (`testes/test_auditoria_final_1_4_2.py` e
> `assets/fundacao-kit/tests/test_auditoria_final_1_4_2.py`):
> - **AF-01** a CLI do kit recusa opção obrigatória ausente com JSON e código 2, não traceback; **AF-09** abrir um
>   projeto no coordenador exige só `read` (identidade de leitura ou auditoria consulta tarefas; escrever continua
>   exigindo `write` em cada operação) — kit **1.4.1**;
> - **AF-02** o instalador descreve a troca como ela é (duas renomeações com uma marca entre elas): exceção na troca
>   devolve a anterior e descarta a cópia preparada; queda do processo entre as renomeações é concluída pelo próximo
>   `instalar`/`atualizar`, e `verificar` avisa; `remover` limpa `~/.agents/skills-preparo/`; **AF-03** a origem precisa
>   declarar `name: fundacao-ia-multiprojetos`; **AF-04** ligação com este nome que aponta para a pasta de outra skill
>   é mantida e relatada;
> - **AF-05** o CEN-11 confere o nome canônico (não o da pasta) e registra como *puladas* as verificações que dependem
>   do perfil; **AF-07** o hook de identidade só nega atribuição e remoção da variável, não a leitura; **AF-08**
>   `FUNDACAO_MCP_PERMITIDAS` aceita padrões (`mcp__ccd_*`) e a capacidade 08 avisa sobre as ferramentas MCP do host;
> - **AF-06** este README alinhado ao `last_verified` do `SKILL.md`; a **licença** da skill passou a **MIT**
>   (`LICENSE.txt` no pacote), por decisão do titular, para publicação.
>
> Resultados na 1.4.3: kit 166 OK (3 pulados), scripts 23, entrega 34, cenários 16/16 (110/110), 258 referências e
> 0 ausentes, `quick_validate` válido nas duas variantes; pacote `.skill` `a2382ebb…621b` (123 arquivos) e completo
> `f49f0c93…692e` (146). Com o OK do titular, a **1.4.3 foi instalada no perfil em 19/10/2026, às 20h05**
> (`atualizar --sha256`, hash conferido antes de extrair; 123 arquivos, 0 divergências); a 1.4.2 ficou em
> `~/.agents/skills-anteriores/`.

> **1.4.2 (19/10/2026):** resposta à auditoria sobre a 1.4.1 (`auditoria/RELATORIO-AUDITORIA-1.4.1.md`
> e o patch `auditoria/PATCH-RECEBIDO-AUDITORIA-1.4.1.patch`), verificada em
> `auditoria/VERIFICACAO-AUDITORIA-1.4.1.md`. O patch **não** foi aplicado: não corresponde ao
> instalador real, nem chega a aplicar, e o código dele não instala a skill. Mudanças:
> - o instalador confere o hash do pacote **antes de extrair**, com `--sha256` e com o
>   `SHA256SUMS.txt` ao lado do pacote, e recusa uma divergência sem alterar nada;
> - instalar e atualizar passaram a preparar a cópia fora das pastas de skills e a trocar por
>   renomeação, com retorno à versão anterior se algo falhar (chamado de "atômico" na época; a 1.4.3
>   corrigiu a descrição: são duas renomeações com uma marca entre elas, AF-02);
> - uma ligação em conflito é recusada antes de copiar, e um pacote corrompido vira erro em JSON;
> - `references/seguranca-isolamento.md` declara o limite de credencial por projeto;
> - um arquivo de texto para revisão por IA de chat acompanha os zips.
>
> Cada correção de código veio com uma regressão que falha na 1.4.1 e passa na 1.4.2. O kit não
> mudou (1.4.0). Com novo OK do titular, a 1.4.2 foi instalada no perfil em 19/10/2026, às 18h29, com
> o hash do pacote conferido antes de extrair; a 1.4.1 ficou em `~/.agents/skills-anteriores/`.

> **1.4.1 (19/10/2026):** resposta ao relatório técnico sobre a 1.4.0
> (`auditoria/RELATORIO-TECNICO-AUDITORIA-1.4.0.md`), verificada e aplicada em
> `auditoria/VERIFICACAO-RELATORIO-TECNICO-1.4.0.md`. Mudanças:
> - o `remover` do instalador trata a instalação manual e o arquivo somente leitura;
> - o `verificar` informa o FTS5 do kit;
> - o §7 do `SKILL.md` separa os dois regimes de identidade;
> - a introdução cita R52–R60;
> - a pedido do titular, `compatibility` foi para dentro de `metadata`, por causa do Chat/Work.
>
> Cada correção de código veio com uma regressão que falha na 1.4.0 e passa na 1.4.1. O kit não
> mudou (1.4.0). Com novo OK do titular, a 1.4.1 foi instalada no perfil em 19/10/2026, às 11h51; a
> 1.4.0 ficou em `~/.agents/skills-anteriores/`.

> **1.4.0 (19/10/2026):** resposta à auditoria externa da 1.3.4 (20 apontamentos, 4 melhorias) e ao
> achado N1 do ensaio com a skill caveman. Tabela item a item — status, teste, ambiente, esperado ×
> observado antes e depois, limites — em `auditoria/RESPOSTA-AUDITORIA-EXTERNA-1.3.4.md`. Cada
> correção de código veio com regressão que falha na 1.3.4 e passa na 1.4.0. Com o OK do titular, a
> 1.4.0 foi instalada no perfil em 19/10/2026, às 10h35; a 1.3.4 ficou em `~/.agents/skills-anteriores/`.

## Síntese

Foi criada uma skill operacional e modular que orienta uma IA executora a **implantar** uma
fundação técnica para vários projetos com IA (fluxo A), **adaptar** projetos existentes
preservando comportamento, dados e integrações (fluxo B) e **operar** a fundação —
verificar, auditar, atualizar, desativar, fazer backup, restaurar e retomar (fluxo C). Ela
traz 11 capacidades técnicas com procedimento de implementação e de verificação, a matriz
R01–R51 do livro (mais R52–R60 da proposta 3.0) com origem por aula e página, modelos de
registro, scripts de apoio e um kit de referência em Python + SQLite.

O que sustenta cada afirmação:
- **Testado em execução, em ambientes descartáveis (1.4.5):** 166 testes do kit (3 pulados:
  link simbólico de arquivo indisponível sem modo de desenvolvedor); 23 testes dos scripts da
  skill (`scripts/tests/`); 40 testes das ferramentas de entrega (`testes/`); 16 cenários
  determinísticos (111/111 verificações). **Histórico, não repetido desde a 1.4.0:** 17 execuções de
  avaliação com subagentes (com e sem a skill, versões 1.0.0 e 1.1.0) dando nota a 51 asserções
  com a skill; simulação de acionamento 20/20 (descrição inalterada desde a 1.2.0).
- **Auditado:** auditoria independente com o `skill-creator` e o `skills-qa` sobre a 1.1.0
  (aprovação condicionada a seis correções); reverificação independente da 1.2.0 (PARCIAL:
  uma regressão alta e achados novos, corrigidos na 1.3.0); terceira conferência independente
  da 1.3.0, de novo com o `skill-creator` e o `skills-qa` (APROVADA COM RESSALVAS: um item
  parcial e nove achados novos, três médios — tratados na 1.3.1); quarta conferência da 1.3.1
  (APROVADA COM RESSALVAS: dois itens ainda parciais — o prazo com entrada grande e uma citação
  —, o texto afirmando além do observado, quatro achados baixos e uma observação), tratados na
  1.3.2; confirmação final da 1.3.2 (APROVADA COM RESSALVAS: os oito itens pedidos corrigidos,
  mas uma regressão média latente no prazo — um neto órfão prendia a resposta — e um achado
  baixo antigo — arquivo acrescentado à cópia passava), tratados na 1.3.3; confirmação focada
  da 1.3.3 (`auditoria/CONFIRMACAO-N7-N8.md`, APROVADA COM RESSALVAS: N7, N8 e observações
  corrigidos, nenhum achado médio ou maior; restaram três resíduos de texto e quatro
  observações baixas). A 1.3.4 trata os resíduos e duas observações (verificador estrito na
  grafia e na raiz para `<skill>/…`; metadados do sistema na cópia não barram a restauração) e
  declara as outras duas como limites — **essas últimas mudanças foram verificadas pelo autor
  (testes que falham na 1.3.3, cenários e controles), sem nova conferência independente.** Os
  lotes de código vieram com testes que falham na versão anterior (os ajustes só de texto não
  têm teste). O que ficou parcial em cada versão e os limites declarados estão em
  `auditoria/RESPOSTA-AOS-ACHADOS.md`. **Auditoria externa da 1.3.4** (Linux, dados fictícios;
  `auditoria/RELATORIO-AUDITORIA-EXTERNA-1.3.4.md`): 6 P1, 14 P2 e 4 melhorias; a 1.4.0 responde
  item a item em `auditoria/RESPOSTA-AUDITORIA-EXTERNA-1.3.4.md`, sem nova conferência independente.
  **Auditoria final da 1.4.2** (sessão independente, Fable 5.1; `auditoria/AUDITORIA-FINAL-1.4.2.md`):
  APROVADA COM RESSALVAS — dez achados P3, nenhum P1 ou P2, números da 1.4.2 todos reproduzidos; os
  achados foram corrigidos na 1.4.3 (bloco acima). **Conferência independente da 1.4.3** (sessão
  independente, Fable 5.1; `auditoria/CONFERENCIA-1.4.3.md`): APROVADA COM RESSALVAS — as nove correções e
  todos os números da 1.4.3 confirmados; um P2 (CF-01) e cinco P3; CF-01 a CF-04 corrigidos na 1.4.4 (bloco
  acima), CF-05 e CF-06 pendentes.
- **Instalado:** a **1.4.5** está instalada neste computador (cópia em `~/.agents/skills`, junção
  em `~/.claude/skills`). Histórico:
  - 18/10: a 1.3.0 às 22h41 e a 1.3.1 às 23h40;
  - 19/10: a 1.3.2 às 00h28, a 1.3.3 à 01h00 e a 1.3.4 à 01h39;
  - 19/10, cada uma com o OK do titular: a 1.4.0 às 10h35, a 1.4.1 às 11h51, a 1.4.2 às 18h29, a 1.4.3 às 20h05 e a
    1.4.4 às 21h36 (esta a pedido direto do titular, depois das correções da conferência da 1.4.3) e a 1.4.5 às
    22h16 (idem, fechando CF-05 e CF-06b).

  Toda instalação teve releitura dos hashes e é reversível com `remover --confirmar`. Para outro
  computador, para o claude.ai e para revisão por outra IA: `transferencia/` (seção 2).
- **Não feito nesta entrega (de propósito):** chamadas reais a provedores, instalação de
  pacotes ou plugins, alteração de configurações, hooks ou servidores MCP do Claude Code,
  download de modelos (salvo o efeito colateral do Docling, seção 10), uso de dados reais.
  Cada um tem condição e comando prontos (seção 9).

### Os seis estados (não se confundem)

| Estado | Situação | Evidência |
|---|---|---|
| Skill criada | **Sim** | 146 arquivos da 1.4.3 à 1.4.5 (`ARVORE-SKILL.md`; 144 da 1.4.0 à 1.4.2; 134 na 1.3.4) |
| Skill validada estruturalmente | **Sim** | `quick_validate` válido na árvore e no pacote extraído (variantes `anthropic-skills` e plugin oficial `ea10b213686c`). Na 1.4.1, as chaves da raiz do cabeçalho também estão na lista do validador do Chat/Work (CEN-11 e pacote extraído; esse validador não rodou aqui). 258 referências conferidas na árvore (257 no pacote), 0 ausentes. As citações `<skill>/…` são conferidas em qualquer lugar, só pela raiz da skill e com a grafia exata: o CEN-08 planta três erros em cada uma das 24 ocorrências — arquivo inexistente, erro na primeira pasta e caixa trocada (72 acusados) — e remove cada um dos 11 arquivos assim citados (11 acusados); varredura de injeção sobre todos os Markdown com 1 aviso revisado |
| Skill testada em execução | **Parcialmente: sim em ambientes descartáveis; nenhuma integração real com provedores** | seção 7 (166 testes do kit, 23 dos scripts, 40 da entrega, 111/111 verificações de cenário, MCP com SDK real em processo e por stdio; avaliações com subagentes só históricas) |
| Skill instalada no ambiente | **Sim, a 1.4.5** (19/10/2026, 22h16; Claude Code deste computador; a pedido do titular) | Antes, `verificar --origem` contra o pacote 1.4.4 arquivado deu 123 arquivos e 0 divergências. Depois, `instalar_skill.py atualizar --sha256 1134a4f1…1ac9` conferiu o hash do pacote antes de extrair, contra o hash informado e contra o `SHA256SUMS.txt` de `dist/`, e fez a troca por renomeação; a área de preparo foi removida. O `verificar --origem dist/fundacao-ia-multiprojetos.skill --sha256 …` deu 123 arquivos, 0 divergências, junção válida e integridade do pacote conferida. O `SKILL.md` lido pela junção tem `version: "1.4.5"`, e `LICENSE.txt` está na cópia. A 1.4.4 guardada em `~/.agents/skills-anteriores/` confere com o pacote dela (123 arquivos, 0 divergências), ao lado das versões 1.3.0 a 1.4.3. Nas atualizações para a 1.4.4 e para a 1.4.5 o Claude Code recarregou o catálogo de skills na própria sessão (na 1.4.5, alguns minutos depois do `atualizar`; `ambiente/instalacao-2026-10-18.json`, `atualizacao_1_4_4` e `atualizacao_1_4_5`). Não verificados: acionamento da 1.4.5 instalada num pedido real, Codex e claude.ai |
| Fundação implementada | **Não** | o kit só foi instalado em pastas de teste; a fundação do usuário será implantada quando a skill for acionada com raiz e escopo autorizados |
| Projeto efetivamente adaptado | **Não** | só projetos fictícios de teste (`evals/fixtures/`); a migração de um projeto real exige evidências próprias sobre a origem |

---

## 1. O que está nesta pasta

| Caminho | Conteúdo |
|---|---|
| `../fundacao-ia-multiprojetos/` | A skill completa (SKILL.md, referências, scripts, modelos, kit de referência, avaliações) |
| `dist/fundacao-ia-multiprojetos.skill` | Pacote instalável no formato Agent Skills (zip com a pasta na raiz; 123 arquivos da 1.4.3 à 1.4.5, 121 na 1.4.2; sem `evals/`) |
| `dist/fundacao-ia-multiprojetos-completo.zip` | A mesma skill com `evals/` (cenários, avaliações e projetos fictícios de teste; o `.env` das fixtures tem valor fictício) |
| `dist/SHA256SUMS.txt` | Hashes dos pacotes |
| `dist/EMPACOTAMENTO.json` | Versão empacotada e ferramenta usada (caminho e hashes do skill-creator) |
| `dist/anteriores/<versão>/` | Conjuntos anteriores arquivados pelo empacotador (a 1.3.4, a 1.4.0, a 1.4.1 e a 1.4.2 estão em `dist/anteriores/<versão>/`, cada uma com o seu `SHA256SUMS.txt`) |
| `MATRIZ-HOSTS-E-VERIFICACOES.md` | Validadores e empacotador com versões e hashes, hosts e formas de instalação, requisitos por peça e matriz do que rodou em cada sistema/versão |
| `testes/` | Testes das ferramentas de entrega: instalador da skill (F17), empacotador (F18), registros de avaliação (F19), relatório técnico da 1.4.0 (COD-02/03/05), auditoria sobre a 1.4.1 (SEC-02, OPS-01) e auditoria final da 1.4.2 (AF-02, AF-03, AF-04) |
| `ARVORE-SKILL.md` | Árvore de arquivos e finalidade de cada componente |
| `rastreabilidade/MATRIZ-RASTREABILIDADE.md` (e `.csv`) | Matriz R01–R51 (+ R52–R60): origem (aula, seção, página), interpretação, arquivo/procedimento, critério, cenário, dependências, adaptação pedagógica, natureza e estado |
| `leitura/REGISTRO-LEITURA.md` | Como as fontes foram lidas, trechos comprometidos e falhas de extração (com os logs) |
| `avaliacoes/AVALIACOES.md` | Procedimento, esperado, observado e evidência de todas as avaliações; real × simulado × mock |
| `auditoria/` | Objetivo original, roteiro, relatório da auditoria independente, correções, resposta aos achados, reverificação, terceira e quarta conferências e as duas confirmações finais |
| `ambiente/inventario-2026-10-18.json` | Inventário somente leitura do ambiente (versões, sistema de arquivos, módulos) |
| `ambiente/instalacao-2026-10-18.json` | Resultado da instalação e da releitura (hashes) da skill neste computador |
| `transferencia/fundacao-ia-multiprojetos-1.4.5.zip` | Para instalar em outro computador: o `.skill` da 1.4.5, o instalador, `SHA256SUMS.txt` e `LEIA-ME.txt` com os passos (SHA-256 do zip `93548ea7…e4e1`); os zips das versões anteriores seguem na pasta |
| `transferencia/fundacao-ia-multiprojetos-1.4.5-para-claude-ai.zip` | O mesmo `.skill` da 1.4.5, byte a byte, com extensão `.zip`, para o envio no claude.ai (SHA-256 `1134a4f1…1ac9`) |
| `transferencia/fundacao-ia-multiprojetos-1.4.5-para-revisao.md` | Os 123 arquivos do pacote, o instalador e o LEIA-ME em texto UTF-8, com o SHA-256 de cada um, para revisão por IA de chat. Não serve para instalar (`0d38243a…4609`) |
| `transferencia/…-1.4.2*`, `…-1.4.1*` e `…-1.4.0.zip` | Anteriores: 1.4.2 (zip `9968bceb…9fca`; claude.ai `6b61af72…d389`; revisão `18fc0355…f69f`), 1.4.1 (`e3b44216…7821`; claude.ai `bce7b510…5f29`) e 1.4.0 (`c5b4b740…8ed6`) |
| `instalar_skill.py` · `empacotar.py` · `gerar_arvore.py` | Instalar/atualizar/verificar/remover · gerar os pacotes · gerar a árvore |

## 2. Instalação

Pré-requisitos: Python 3.10+ com SQLite/FTS5 (o instalador confere a versão antes de alterar
qualquer coisa e reconhece a junção do Windows também no 3.10/3.11, sem `os.path.isjunction`).
Opcionais: `mcp` 2.x, que exige Python 3.11+ (servidor MCP do kit); `torch` + `transformers` + um
modelo local autorizado (CAG real). Requisitos por peça e o que rodou em cada versão:
`MATRIZ-HOSTS-E-VERIFICACOES.md`.

**Atualizar a cópia instalada** (guarda a anterior em `~/.agents/skills-anteriores/`; foi o comando
usado em 19/10, sempre com o OK do titular, para passar à 1.4.0 às 10h35, à 1.4.1 às 11h51 e à 1.4.2
às 18h29, esta com `--sha256`, à 1.4.3 às 20h05, com
`--sha256 a2382ebbbf7b65a7eb61f6f954723857600be890911a2afaf39436075575621b`, à 1.4.4 às 21h36, a pedido do
titular, com `--sha256 b54b1714b466c411af49aab3c46fade3581e44f9527d04b75e501472d730401c`, e à 1.4.5 às 22h16, com
`--sha256 1134a4f1cea654778499091dfd52ffe3c622a13fb7e7af6d4981ed1b556a1ac9`):

Desde a 1.5.0, `instalar` e `atualizar` **exigem** `--sha256` com o hash publicado do pacote (linha do
`.skill` em `dist/SHA256SUMS.txt` ou o hash informado por quem publicou): o `SHA256SUMS.txt` ao lado do pacote
viaja no mesmo canal e só detecta corrupção. Pasta como origem só com `--pasta-de-desenvolvimento-nao-verificada`
(a saída avisa "ORIGEM NÃO VERIFICADA"). O pacote é lido uma vez e conferido antes de extrair: nomes não
portáveis, duplicatas, links e mais de 10.000 entradas ou 100 MiB são recusados. Na raiz desta entrega:

```powershell
python entrega\instalar_skill.py atualizar --origem entrega\dist\fundacao-ia-multiprojetos.skill --sha256 <hash do .skill>
```

**Claude Code neste computador** (mesma convenção das outras skills do perfil: cópia física
em `~/.agents/skills` e junção em `~/.claude/skills`):

```powershell
python entrega\instalar_skill.py instalar --origem entrega\dist\fundacao-ia-multiprojetos.skill --sha256 <hash do .skill>
```

```powershell
python entrega\instalar_skill.py verificar --origem entrega\dist\fundacao-ia-multiprojetos.skill --sha256 <hash do .skill>
```

O script não baixa nada, recusa sobrescrever uma instalação existente (use `atualizar`), exige que a
origem declare `name: fundacao-ia-multiprojetos` (1.4.3; desde a 1.4.4 o `SKILL.md` em UTF-8 com BOM é aceito e,
sem `name` legível, a recusa diz isso) e compara os hashes da cópia instalada. Desde a
1.4.2, antes de extrair, confere o pacote contra o `SHA256SUMS.txt` ao lado dele (o de `dist/` lista o
`.skill`) e contra `--sha256 <hash>`, se informado; divergência ou pacote corrompido recusa a operação
sem alterar nada. A troca é feita por renomeação: a cópia nova é preparada em `~/.agents/skills-preparo/`,
conferida e só então posta no lugar — a anterior vai para `~/.agents/skills-anteriores/` e a preparada
entra no lugar dela (duas renomeações, com uma marca entre elas). Uma falha antes da troca não altera
nada; uma exceção na troca ou na ligação devolve a versão anterior e descarta a cópia preparada; se o
processo cair entre as duas renomeações, o próximo `instalar` ou `atualizar` conclui a troca com a cópia
preparada, e `verificar` avisa enquanto isso não acontecer (1.4.3, AF-02; se a marca da troca estiver ilegível,
as cópias preparadas que sobrarem em `skills-preparo/` são removidas e relatadas — 1.4.4, CF-04). **Neste computador a
instalação já foi feita** (1.3.0 às 22h41 de 18/10/2026, atualizada até a 1.4.5 às 22h16 de 19/10; ver
`ambiente/instalacao-2026-10-18.json`): o primeiro comando agora recusaria, e o segundo serve para
reconferir. Em geral a skill passa a valer na próxima sessão (ou após
`/reload-skills`); aqui, o Claude Code passou a listá-la na própria sessão da instalação.

**Manual (qualquer sistema):** extraia o `.skill` (é um zip) de modo que exista
`<pasta-de-skills>/fundacao-ia-multiprojetos/SKILL.md`. Pastas lidas: Claude Code —
`~/.claude/skills/` (pessoal) ou `.claude/skills/` (projeto); Codex — `~/.agents/skills/`
ou `.agents/skills/` (compatibilidade projetada, **não testada**).

**Outro computador:** `transferencia/fundacao-ia-multiprojetos-1.4.5.zip` traz o `.skill` da 1.4.5,
o `instalar_skill.py`, o `SHA256SUMS.txt` e o `LEIA-ME.txt`. Os passos do LEIA-ME: conferir o hash
(Windows, Linux e macOS), instalar com `--sha256`, verificar, enviar ao claude.ai, pedir revisão a
outra IA e remover; ele traz também uma tabela de onde foi testado. O zip foi reaberto e conferido
aqui: hashes extraídos, `sha256sum -c` (GNU, pelo Git Bash) e, num perfil descartável, o ciclo
recusa com `--sha256` errado → instalar → verificar → remover, com o instalador extraído. A
instalação em outro computador e o `shasum` do macOS não foram testados. Montado por
`fundacao-ia-multiprojetos-workspace/auditoria-final-1.4.2/ferramentas/montar_transferencia_1_4_3.py`
(adaptado do montador da 1.4.2, em `…/auditoria-1.4.1/ferramentas/`); os zips anteriores continuam ao lado.

**Revisão por outra IA:** zip anexado numa conversa de chat pode chegar ilegível; foi o que aconteceu
na auditoria sobre a 1.4.1 (ING-01). Para pedir uma auditoria, anexe
`transferencia/fundacao-ia-multiprojetos-1.4.5-para-revisao.md`. Ele tem os 123 arquivos do pacote,
o instalador e o LEIA-ME em texto, com o SHA-256 de cada um, e o montador confere que cada bloco
reproduz o arquivo byte a byte. Não serve para instalar.

**claude.ai (Chat/Work):** envie `transferencia/fundacao-ia-multiprojetos-1.4.5-para-claude-ai.zip`,
que é o mesmo `.skill` com extensão `.zip`. No claude.ai: Customize > Skills, botão "+", "Create
skill" e "Upload a skill". O recurso exige a execução de código ligada (Settings > Capabilities).
Passos conferidos na central de ajuda em 19/10/2026
(https://support.claude.com/en/articles/12512180-using-skills-in-claude). O envio **não foi
testado** aqui. Desde a 1.4.1, o cabeçalho só tem na raiz chaves que o validador desse catálogo
aceita (`MATRIZ-HOSTS-E-VERIFICACOES.md` §1). Lá, a skill roda no ambiente de execução de código
da nuvem, sem acesso às pastas do seu computador.

**Remoção:** `python instalar_skill.py remover --confirmar`. Remove a junção, a cópia, uma
instalação manual desta skill em `~/.claude/skills` e as sobras de `~/.agents/skills-preparo/`; uma
ligação com este nome que aponte para a pasta de outra skill é mantida e relatada (1.4.3), mas uma ligação
pendurada (alvo que não existe mais) é removida — só a ligação — e relatada (1.4.4, CF-02); informa cada
caminho e sai com código 1 se algo ficar no lugar.

## 3. Uso

Peça em linguagem natural (a descrição da skill aciona o uso) ou invoque
`/fundacao-ia-multiprojetos <pedido>` no Claude Code. A skill escolhe o fluxo:

- **A — Implantar** a fundação e criar projetos (A1–A8);
- **B — Adaptar** um projeto existente (diagnóstico → planejamento → implementação e comparação → encerramento; B1–B10);
- **C — Operar**: verificar, auditar, atualizar, desativar/substituir, backup e restauração, retomar, novo projeto, promoção (C1–C11).

Cada etapa dos fluxos A e B traz entradas, ações, saídas, critério de conclusão e tratamento
de falhas. Pontos que dependem de você (a skill pergunta uma vez e prepara o resto
enquanto isso): raiz autorizada; identidade do titular (`FUNDACAO_PRINCIPAL`, definida por
você no terminal); dados fictícios × reais (reais só após
`assets/templates/CHECKLIST-DADOS-REAIS.md`); provedores, rotas e teto de chamadas pagas.

## 4. Exemplos prontos de invocação

**Criar uma fundação**
> Use a skill fundacao-ia-multiprojetos para implantar a fundação em `D:\IA\fundacao` com
> os projetos `juridico-lab` e `reversa-lab`, só com dados fictícios. Sou o titular
> (identidade `titular`). Tenho Claude Code e Codex instalados, mas ainda não autorizo
> chamadas pagas. Deixe a RETOMADA pronta para eu continuar amanhã.

**Criar um projeto**
> Na fundação em `D:\IA\fundacao`, crie o projeto `atendimento-lab` a partir do modelo,
> com leitura e escrita só para `operador-atendimento` e aprovação para
> `revisor-atendimento`. Mostre a prova negativa de acesso a partir dos outros projetos.

**Adaptar um projeto existente**
> Adapte o projeto em `D:\projetos\squad-peticoes` à fundação em `D:\IA\fundacao`.
> Trabalhe numa cópia, preserve o comportamento atual (caracterize antes e compare
> depois), não copie segredos e me mostre o diagnóstico e o plano antes de mexer no original.

**Auditar uma implementação**
> Audite a fundação em `D:\IA\fundacao` sem alterar nada: estado de cada requisito
> R01–R51 com evidência, o que é real × simulado × bloqueado, integridade dos eventos,
> isolamento entre projetos e um ensaio de restauração em pasta separada. Entregue o relatório.

## 5. Atualização

- **Numeração:** a versão da skill (`metadata.version` no `SKILL.md`) sobe a cada entrega; a do kit de
  referência (`KIT_VERSION` em `assets/fundacao-kit/fundacao/__init__.py`) só sobe quando algum arquivo do
  kit muda (as skills 1.4.1 e 1.4.2 mantiveram o kit 1.4.0; a 1.4.4 manteve o 1.4.1, por decisão do titular
  em 19/10/2026). Assim, uma cópia restaurada só acusa "kit diferente" quando o kit mudou de fato.
- **Da skill:** gere/obtenha o pacote novo e rode `instalar_skill.py atualizar --origem <pacote> --sha256 <hash>`
  (a versão anterior fica guardada, com data, em `~/.agents/skills-anteriores/` — fora da pasta
  de skills, para não ser lida como uma segunda skill). Depois:
  `python <skill>/scripts/verificar_referencias.py` e o `quick_validate` do skill-creator.
  Validade dos fatos voláteis: `metadata.last_verified` = 2026-10-20, janela de 3 meses —
  reconfira `references/fontes-verificadas.md` até 20/01/2027 ou antes de decisões de custo
  ou termos. Licença da skill: MIT desde a 1.4.3 (`LICENSE.txt` na raiz da skill e no pacote). Os campos de frescor ficam dentro de `metadata` (o padrão Agent Skills exige
  mapa de textos e o `quick_validate` recusa chaves extras no cabeçalho); para publicar pelo
  legal-builder-hub, gere uma cópia com esses campos no formato do hub.
- **Do kit numa fundação existente, em um comando (1.5.0):** `python <skill>/scripts/atualizar_fundacao.py
  checar --raiz <raiz>` só lê (versões, o que muda arquivo a arquivo, alteração local, identidade e cadeia de
  eventos); `aplicar --raiz <raiz> --backups <pasta em outro disco>` faz backup ANTES verificado, ensaia o kit
  novo numa cópia restaurada (`init`, cadeia e suíte; falha que já existia não bloqueia, regressão bloqueia sem
  tocar a raiz), promove, faz backup DEPOIS e grava o registro em `<raiz>/evidence/atualizacoes/`;
  `desfazer --registro <arq>` devolve o código se o esquema do banco não mudou. Passo a passo, se preferir:
- **Do kit, passo a passo:** `python <skill>/scripts/instalar_kit.py --destino <raiz>`
  monta o plano antes de escrever: com conflito (código alterado localmente) **nada é escrito**
  e a saída é o código 3 com o plano; ligação ou junção que leve para fora do destino recusa
  tudo (código 4). Depois da decisão (fluxo C6), `--atualizar` substitui os arquivos de código e
  guarda a versão anterior em `registry/kit_backup/<data>-<sufixo>/` (código 5 com `desfeito: false` e
  `composicao: "indeterminada"`: o retorno também falhou — siga `erros` e `acao_necessaria`); `--manter-conflitos` aceita um
  estado misto registrado (código 3). A configuração local (`registry/`) nunca é sobrescrita, e
  a versão só é declarada com a composição conferida (código 0). Componente habilitado cujo
  código mudou precisa ser habilitado de novo (o registro guarda o hash do código aprovado).
  Em seguida rode `python -m fundacao init` na raiz
  (idempotente): migra o banco (migrações 3 e 4 na 1.4.0), exporta decisões protegidas pendentes,
  cria a identidade do registro de retiradas, se faltar, repara derivados de memórias já
  retiradas e preenche as retiradas e revogações que estão no banco e faltam no registro — sem
  isso o `backup criar` recusa. Faça
  um backup novo: cópias anteriores à 1.3.0 não têm a identidade do registro anotada e, se não
  tiverem retiradas, só restauram com `--aceitar-registro-nao-comprovado`, depois de conferir o
  registro à mão; cópias anteriores à 1.3.1 não têm o hash do banco e são conferidas só por
  contagens (a verificação avisa). Se a restauração de uma cópia antiga trouxer
  `acao_necessaria`, a raiz restaurada voltou com o kit da cópia: atualize o kit nela e rode
  `init` antes de usá-la. Rode a suíte (`python -B -m unittest discover -s tests`) e trate a
  atualização do modelo de projeto separadamente da migração das instâncias
  (`python -m fundacao projeto drift --id <projeto>`). Bancos antigos recebem a migração 2
  (chaves de idempotência por projeto) automaticamente ao abrir.

## 6. Retomada

Cada sessão termina com `RETOMADA.md` na raiz da fundação (objetivo, versão, estado
confirmado, evidências, bloqueios, próxima ação e efeitos já realizados). Valide com
`python <skill>/scripts/retomada.py validar --arquivo <raiz>/RETOMADA.md` e peça:
> Retome a fundação em `D:\IA\fundacao` a partir da RETOMADA.md.

A skill confere os arquivos citados antes de agir e não repete efeitos já realizados.

## 7. Avaliações e evidências

Detalhe completo em `avaliacoes/AVALIACOES.md`. Resumo:

| Verificação | Resultado | Natureza |
|---|---|---|
| Suíte de conformidade do kit 1.4.1 (árvore e pacote extraído da skill 1.4.5; o mesmo na 1.4.4 e na 1.4.3) | 166 testes OK, 3 pulados (link simbólico de arquivo indisponível) | real-local; identidades de ensaio; inclui os 3 testes da auditoria final da 1.4.2 (AF-01, AF-09), os 48 testes novos da auditoria externa e do N1 (40 regressões que falham na 1.3.4, 5 controles que passam nas duas versões, 2 pulados e 1 complementar de caminho novo) e as provas reais de prazo, neto órfão e entrada padrão byte a byte das versões anteriores |
| Testes dos scripts da skill e das ferramentas de entrega | 23 + 40 OK (os 6 novos da 1.4.4 são as regressões CF-01 a CF-04 da conferência da 1.4.3) | real-local; perfis, destinos e `dist` descartáveis; junções reais; ausência de `os.path.isjunction` e Python < 3.10 simulados |
| Cenários determinísticos CEN-01–CEN-16 (1.4.5; o mesmo na 1.4.4) | 16/16 (111/111 verificações; as que dependem do perfil aparecem como puladas quando ele não tem o validador ou o book-to-skill) | real-local; alguns com eventos ou rotas simulados (rotulados) |
| Avaliações com subagentes, iteração 1 (E1–E8) | com a skill 46/46; sem a skill 39/42 (E1–E7); custo pareado +732,5 s e +66.837 tokens por execução (E1–E7) | execução real de agentes (skill 1.0.0) em pastas descartáveis; não repetida na 1.4.0; reanálise em `avaliacoes/AVALIACOES.md` §8 |
| Avaliação 9 (instrução embutida em conteúdo autorizado), iteração 2 | 4/5 nas duas configurações | idem; correção aplicada na 1.2.0 |
| Acionamento (20 pedidos, 16 skills concorrentes) | 20/20 | simulação por agente separado, não o mecanismo do host |
| Ensaio MCP (servidor da fundação por stdio) | descoberta, chamada, negativa e encerramento OK; versão negociada 2026-07-28 | real-local (SDK 2.3.0) |
| Opções de isolamento dos adaptadores nas CLIs instaladas | presentes no `--help` (e `--max-turns` no executável do Claude); Codex lê o prompt da entrada padrão | só leitura de ajuda e do executável; nenhuma chamada de modelo |
| Instalação da skill (1.3.0 e atualizações até a 1.4.3) | 0 divergências em todas (111 arquivos nas 1.3.x, 121 da 1.4.0 à 1.4.2, 123 na 1.4.3; desde a 1.4.2, hash do pacote conferido antes de extrair); listada pelo Claude Code, inclusive na sessão da atualização para a 1.4.3 | real-local |
| Backup em pasta de rede (UNC, `localhost/C$`) | criar, verificar e restaurar pela CLI; `backup_sqlite.py` copia | real-local |

## 8. Auditoria

A auditoria independente (agente separado) invocou o `anthropic-skills:skill-creator` e o
`legal-builder-hub:skills-qa` pela ferramenta Skill. Veredito sobre a 1.1.0: **aprovação
condicionada** (0 crítico, 6 altos, 9 médios, 13 baixos; skills-qa: SOME CONCERN). A
reverificação independente da 1.2.0 (`auditoria/REVERIFICACAO-AUDITORIA.md`) deu **PARCIAL**:
quatro dos seis altos corrigidos, uma regressão alta (cópia vazia com `#` no caminho), quatro
achados médios novos e a instalação declarada sem ter ocorrido. A terceira conferência
(`auditoria/TERCEIRA-CONFERENCIA.md`, sobre a 1.3.0, com nova invocação do `skill-creator` e do
`skills-qa`) deu **APROVADA COM RESSALVAS**: das 17 pendências da reverificação, 16 corrigidas e
1 parcial (RG-3), mais três achados médios novos (banco da cópia não conferido contra o
manifesto; prazo que não encerrava o neto de uma CLI `.cmd`; caminho de rede) e seis baixos.
A 1.3.1 tratou esses achados com testes que falham na 1.3.0. A quarta conferência
(`auditoria/QUARTA-CONFERENCIA.md`, sobre a 1.3.1) deu **APROVADA COM RESSALVAS**: 7 itens
corrigidos, 2 ainda parciais (o prazo não valia com entrada maior que o buffer do pipe e uma
CLI que não a lê; uma das 24 citações `<skill>/…` escapava do verificador), o texto da entrega
afirmando além do observado, quatro achados baixos (kit da cópia na raiz restaurada, cópias
antigas conferidas só por contagens sem aviso, manifesto malformado fora do contrato,
contagem desatualizada no R42) e uma observação (destino em rede). A 1.3.2 tratou todos, com
testes que falham na 1.3.1 (os ajustes só de texto não têm teste). A confirmação final
(`auditoria/CONFIRMACAO-FINAL.md`, sobre a 1.3.2) deu **APROVADA COM RESSALVAS**: os oito itens
pedidos corrigidos, mas uma regressão média e latente que a própria 1.3.2 introduziu — a CLI
termina e deixa um neto órfão com as saídas abertas, e a chamada só voltava quando ele
terminava, sem encerrá-lo — e um achado baixo antigo (arquivo acrescentado à cópia, fora do
manifesto, passava e era restaurado), mais observações (erro na primeira pasta de `<skill>/…`
escapava; aviso de rede para destino local com o prefixo de caminho longo) e redação. A 1.3.3
trata todos: o Job Object no Windows encerra todos os descendentes ao fim da chamada (nos
demais sistemas, o grupo de processos — ramo não executado aqui, que não alcança descendente
com sessão própria); a verificação lista e recusa arquivos extras; o verificador confere
`<skill>/…` qualquer que seja a primeira pasta; o aviso de rede só vale para rede de verdade.
A confirmação focada da 1.3.3 (`auditoria/CONFIRMACAO-N7-N8.md`) deu **APROVADA COM
RESSALVAS** — N7, N8 e observações corrigidos; nenhum achado médio ou maior — e deixou três
resíduos de texto e quatro observações: o verificador tolerante (citação que só existe em
`references/` ou com caixa trocada passava), a pasta temporária que sobra se o Job Object for
recusado, a fração de milissegundo antes de a CLI entrar no Job Object e metadados do sistema
(`Thumbs.db` etc.) numa cópia em pasta de rede barrando a restauração. A 1.3.4 corrige os
resíduos e a primeira e a última observações (com testes que falham na 1.3.3) e declara as
outras duas como limites; essas mudanças não passaram por nova conferência independente.
Ficam limites declarados: ao abrir em modo somente leitura uma origem em WAL que
estava fechada, o próprio SQLite cria `-wal`/`-shm` vazios ao lado dela (listados na saída do
`backup_sqlite.py`); alterações de arquivos depois da cópia, como a política de rotas, não
são reaplicadas (a restauração as lista em `nao_reaplicado`); manifesto e banco na mesma pasta
podem ser forjados juntos (proteja as cópias); o encerramento da árvore no Linux não foi
executado. As correções de cada rodada e as verificações repetidas estão em
`auditoria/RESPOSTA-AOS-ACHADOS.md`.

**Auditoria externa da 1.3.4** (`auditoria/RELATORIO-AUDITORIA-EXTERNA-1.3.4.md`, com o pacote de
evidências E01–E07 guardado em `fundacao-ia-multiprojetos-workspace/auditoria-externa-1.3.4/evidencias-auditor/`):
20 apontamentos (6 P1, 14 P2) e 4 melhorias, mais o achado N1 do ensaio do titular com a skill
caveman. A 1.4.0 reproduziu cada um com regressão própria (vermelha na 1.3.4, verde na 1.4.0) e
corrigiu a causa; a resposta item a item, com o alcance de cada verificação e o que não foi testado,
está em `auditoria/RESPOSTA-AUDITORIA-EXTERNA-1.3.4.md`. Sem nova conferência independente.

**Relatório técnico sobre a 1.4.0** (`auditoria/RELATORIO-TECNICO-AUDITORIA-1.4.0.md`; 12 apontamentos
com patches sugeridos), verificado em `auditoria/VERIFICACAO-RELATORIO-TECNICO-1.4.0.md` com sondas em
perfil descartável: 4 confirmados (COD-02, COD-05, PKG-03, PRM-03), 3 parciais (PRM-01, PRM-02, COD-03),
5 não confirmados e 1 achado novo (N1, teste de FTS5 do `LEIA-ME`). Seis dos patches sugeridos
quebrariam algo ou enfraqueceriam a verificação. As correções foram aplicadas na **1.4.1**, com o OK
do titular, e o resultado está na seção 7 da verificação.

**Auditoria sobre a 1.4.1** (`auditoria/RELATORIO-AUDITORIA-1.4.1.md`, 8 apontamentos, veredito
"reprovado", com o patch `auditoria/PATCH-RECEBIDO-AUDITORIA-1.4.1.patch`), verificada em
`auditoria/VERIFICACAO-AUDITORIA-1.4.1.md` com sondas em perfil descartável. O auditor recebeu o zip
como texto picado (ING-01), e o lado "antes" do patch não é o instalador real. Resultado:
- **confirmados:** OPS-01;
- **parciais:** SEC-02 e ING-01, cujo efeito prático é a revisão por chat;
- **não confirmados:** SEC-01 (o pacote com os nomes do próprio relatório não escreveu nada fora),
  SPEC-01, ARCH-01, ARCH-02 (limite declarado no texto) e DOC-01;
- **patch:** rejeitado. Não aplica (`patch` acusa fim inesperado), e o código dele não extrai o
  `.skill`, quebra no `--uninstall` e nunca chama a sua proteção contra Zip-Slip.

As correções entraram na **1.4.2**, com regressões que falham na 1.4.1.

**Auditoria final da 1.4.2** (`auditoria/AUDITORIA-FINAL-1.4.2.md`; sessão independente, Fable 5.1, só
leitura sobre o projeto, com sondas e registros em `fundacao-ia-multiprojetos-workspace/auditoria-final-1.4.2/`):
**APROVADA COM RESSALVAS** — todos os números declarados para a 1.4.2 reproduzidos (kit, scripts, entrega,
cenários, referências, hashes, cópia instalada), 38 sondas próprias com marcadores-canário e falhas
injetadas, nenhum segredo real; dez achados P3 (AF-01 a AF-10) e nenhum P1 ou P2. As correções entraram na
**1.4.3**, com regressões que falham na 1.4.2 (seção 10 do relatório).

**Conferência independente da 1.4.3** (`auditoria/CONFERENCIA-1.4.3.md`; sessão independente, Fable 5.1, só
leitura, em cópias e perfis descartáveis, com ferramentas e registros em
`fundacao-ia-multiprojetos-workspace/conferencia-1.4.3/`): **APROVADA COM RESSALVAS** — as nove correções AF-01
a AF-09 estão no código, falham no snapshot da 1.4.2 e passam na 1.4.3; todos os números declarados foram
reproduzidos; a cópia pública é consistente com o original e com o remoto. Ressalvas: um **P2** (CF-01: a
correção AF-07 estreitou demais o `guarda_identidade.py` e deixou passar formas de atribuição que a 1.4.2
negava) e cinco **P3** (CF-02 ligação pendurada mantida pelo `remover`; CF-03 `SKILL.md` com BOM recusado com
mensagem enganosa; CF-04 cópia preparada órfã depois de marca ilegível; CF-05 redação; CF-06 cópia pública além
do declarado). CF-01 a CF-04 foram corrigidos na **1.4.4**, com regressões em `testes/test_conferencia_1_4_3.py`
(vermelhas no snapshot da 1.4.3, verdes na 1.4.4) e uma verificação nova no CEN-13; registros em
`fundacao-ia-multiprojetos-workspace/correcoes-1.4.4/`. Do CF-06, o bloco "Cópia pública" do README da cópia
pública passou a ser produzido pelo montador (`correcoes-1.4.4/ferramentas/montar_copia_publica_1_4_4.py`) já na
1.4.4. CF-05 (redação: bloco 1.4.2 deste README, R46 do gerador e da rastreabilidade, versão do plugin na matriz de
hosts) e CF-06b (`.gitattributes` da cópia pública guardando os logs byte a byte) foram fechados na **1.4.5**, com o
kit mantido em 1.4.1 por decisão do titular (registros em `fundacao-ia-multiprojetos-workspace/correcoes-1.4.5/`).

## 9. Bloqueios e o que falta executar no seu ambiente

| Item | Estado | Condição para destravar | Comando/ação pronta |
|---|---|---|---|
| R12 e R17 — dois provedores reais e continuidade entre eles | bloqueado | autorizar 4 chamadas (2 por provedor) com teto; antes, provar o isolamento do adaptador com um documento-canário de outro projeto | na fundação: política de rotas com `cli_assinatura` habilitada só para o titular e os adaptadores de `fundacao/adapters/cli.py` (prompt pela entrada padrão, ambiente mínimo); a skill conduz o ensaio (fluxo A, capacidade 03) |
| Separação de papéis com dados reais | lógica da política (o hook de identidade é guarda-corpo contornável) | rodar a sessão com outra conta do SO, sem escrita no banco, ou exigir aprovação com credencial fora do alcance do executor | `references/seguranca-isolamento.md` |
| R34 — MCP pelo host | parcial (ensaio local OK) | decidir registrar o servidor no Claude Code/Codex | `claude mcp add --scope project fundacao -- python -m fundacao.mcp_servidor --raiz <raiz>` (conferir a sintaxe na versão instalada antes) |
| R33/R52 — hooks nativos | lógica testada; disparo nativo pendente | aprovar a alteração de `.claude/settings.json` do projeto | bloco de configuração em `references/capacidades/08-…md` §2 |
| Preparo do host no Windows: chave, âncora, hooks e perfis (1.6.0) | testado (simulação, `-SemUAC`, recusa sem administrador); conferido só lendo nesta máquina | o titular roda o script no PowerShell comum (UAC só se a âncora precisar) | `fundacao-ia-multiprojetos/assets/host/windows/preparar-maquina.ps1`; passos em `references/fluxo-a-implantar.md` §Host |
| Preparo do Ubuntu do WSL2: pacotes, `wsl.conf`, Claude Code fixado e lançador (1.6.0) | testado (simulação e execução descartável sem sudo, no bash do Git); não executado no WSL de verdade | o titular roda o script no Ubuntu (sudo) e depois `wsl --terminate` no Windows | `fundacao-ia-multiprojetos/assets/host/wsl/preparar-wsl.sh`; passos em `references/fluxo-a-implantar.md` §Host |
| R36 — plugins | pendente | aprovar instalação de plugin de teste | procedimento em `references/capacidades/08-…md` §5 |
| R26/R27 — CAG com modelo real | parcial (mecanismo sintético OK) | escolher e autorizar um modelo local (0,5–1,5 B, licença registrada) | `python <skill>/scripts/cag_kv_demo.py --modelo <pasta> --corpus ... --testar-invalidacao` |
| R55 — treino desligado nas contas | depende do titular | conferir nas telas das contas | checklist em `assets/templates/CHECKLIST-DADOS-REAIS.md` |
| R59 — Ubuntu/WSL | pendente | ambiente Linux disponível | rodar a suíte e os cenários no WSL2 |
| Cópia instalada na 1.4.0 | **feito** em 19/10/2026, 10h35, com o OK do titular | — | registro em `ambiente/instalacao-2026-10-18.json` (`atualizacao_1_4_0`) |
| Correções do relatório técnico sobre a 1.4.0 (1.4.1) | **feito** em 19/10/2026, com o OK do titular (com o Chat/Work) | — | `auditoria/VERIFICACAO-RELATORIO-TECNICO-1.4.0.md` §7 |
| Cópia instalada na 1.4.1 | **feito** em 19/10/2026, 11h51, com o OK do titular | — | registro em `ambiente/instalacao-2026-10-18.json` (`atualizacao_1_4_1`) |
| Correções da auditoria sobre a 1.4.1 (1.4.2) | **feito** em 19/10/2026 | — | `auditoria/VERIFICACAO-AUDITORIA-1.4.1.md` |
| Cópia instalada na 1.4.2 | **feito** em 19/10/2026, 18h29, com o OK do titular | — | registro em `ambiente/instalacao-2026-10-18.json` (`atualizacao_1_4_2`) |
| Correções da auditoria final da 1.4.2 (1.4.3) | **feito** em 19/10/2026 | — | `auditoria/AUDITORIA-FINAL-1.4.2.md` §10 |
| Cópia instalada na 1.4.3 | **feito** em 19/10/2026, 20h05, com o OK do titular | — | registro em `ambiente/instalacao-2026-10-18.json` (`atualizacao_1_4_3`) |
| Correções da conferência da 1.4.3 (1.4.4) | **feito** em 19/10/2026: código, regressões (vermelhas no snapshot da 1.4.3, verdes na 1.4.4), suítes em cópias e perfis descartáveis, pacote `b54b1714…401c` conferido, transferência e cópia pública sincronizada | — | `auditoria/CONFERENCIA-1.4.3.md` §7; registros em `fundacao-ia-multiprojetos-workspace/correcoes-1.4.4/` |
| Cópia instalada na 1.4.4 | **feito** em 19/10/2026, 21h36, a pedido do titular | — | registro em `ambiente/instalacao-2026-10-18.json` (`atualizacao_1_4_4`) |
| Pendências da conferência da 1.4.3 (1.4.5: CF-05, CF-06b e decisão sobre a versão do kit) | **feito** em 19/10/2026, a pedido do titular; kit mantido em 1.4.1 | — | registros em `fundacao-ia-multiprojetos-workspace/correcoes-1.4.5/` |
| Cópia instalada na 1.4.5 | **feito** em 19/10/2026, 22h16, a pedido do titular | — | registro em `ambiente/instalacao-2026-10-18.json` (`atualizacao_1_4_5`) |
| Skill no claude.ai (Chat/Work) | não testado | o titular envia o ZIP no catálogo | `transferencia/fundacao-ia-multiprojetos-1.4.5-para-claude-ai.zip`; passos na seção 2 |
| Python 3.10/3.11 real (instalador e suíte) | só simulado | um Python 3.10 ou 3.11 disponível | rodar `testes/` e a suíte do kit nele |
| Avaliações comportamentais da 1.4.0 | não repetidas | autorizar o custo (rodada completa ≈ 22 milhões de tokens; subconjunto ≈ 11 milhões) | `avaliacoes/AVALIACOES.md` §8 lista os cenários a repetir primeiro |

## 10. Invocações de habilidades efetivamente realizadas

| Habilidade | Onde | Como |
|---|---|---|
| `book-to-skill` | sessão principal | invocada pela ferramenta Skill; `extract.py` em modo técnico (Docling) **falhou** (`std::bad_alloc`, p79–92) e em modo texto funcionou; `scan_generated_skill.py` usado no CEN-11 (com espelho para cobrir todos os Markdown); instalação no padrão dele (cópia em `~/.agents/skills` e junção em `~/.claude/skills`, com releitura) e pastas de extração temporárias apagadas no fim |
| `anthropic-skills:skill-creator` | sessão principal, auditor e terceira conferência | invocada pela ferramenta Skill na sessão principal (organização, avaliações), pelo auditor (1.1.0) e pela terceira conferência (revisão final da 1.3.0: estrutura e descrição adequadas; ressalva às avaliações antigas sem variância e ao acionamento só simulado); scripts usados: `quick_validate` (em todas as versões, na árvore e no pacote), `aggregate_benchmark`, `generate_review --static`, `package_skill`; método `agents/grader.md` pelos avaliadores |
| `legal-builder-hub:skills-qa` | auditor e terceira conferência | invocada pela ferramenta Skill pelo auditor independente (1.1.0) e pela terceira conferência (1.3.0), com o procedimento completo: SOME CONCERN nas duas; na sessão principal, as instruções foram lidas do arquivo. Não reaplicada depois da 1.3.0 |

Efeito colateral registrado: a tentativa com Docling baixou ~506 MB de modelos de layout para
`~/.cache/huggingface/hub` (detalhes em `leitura/REGISTRO-LEITURA.md`).
