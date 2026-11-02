# Mudanças da 1.7.10

Versão: 1.7.10 · Anterior: 1.7.9 · Registro: 2026-11-01, liberada por decisão do titular ("vamos finalizar ela com o
que temos (mas, obviamente, sendo uma versão funcional) e publicar ela e instalar nessa fundação"), com o lote B da
rodada de segurança fora e os limites abaixo. Escopo, desenho, contratos e rodadas: pasta `outputs/inicio-1.7.10/` do
projeto fundacao-de-ia da fundação (fora desta árvore); revisão de segurança: `entrega/auditoria/REVISAO-SEGURANCA-1.7.10.md`.

## Mudanças

| # | Componente | O que mudou | Motivo observado (onde) | Efeito observado (onde) | Veredito |
|---|---|---|---|---|---|
| M1 | `fundacao-ia-multiprojetos/assets/host/preparo_host.py` e `assets/host/windows/preparar-projeto.ps1` | perfil, lançador e área do titular por projeto; `registry/projetos-host.json`; `-TrocarProjeto` com o plano inteiro antes de gravar | seis projetos migrados com isolamento só lógico (seção 0 do escopo da 1.7.10) | testes do host nos dois sistemas (326 na junção da rodada 3) e revisões dos pacotes; preparo real do titular ainda não rodado | sem efeito observado |
| M2 | `fundacao-ia-multiprojetos/assets/host/wsl/porteiro.py`, `fundacao/porteiro_cliente.py`, `core/auth.py`, `core/trava_banco.py` | porteiro com identidade `sessao-<p>`, trava de projeto, fila tipada e trava do banco | a sessão do projeto chegava ao banco comum com a identidade do lançador | suítes do porteiro nos dois sistemas; a passada de segurança achou três caminhos pelo kit, corrigidos na rodada 4 (R1710-POR-01 a 03) | ajudou |
| M3 | `fundacao-ia-multiprojetos/assets/hooks/` | hooks `guarda_leitura`, `guarda_rede`, `guarda_ferramentas` e `aviso_copia`; `guarda_identidade` com recursão sobre a raiz, barra invertida do Bash e teto de tamanho | leitura entre projetos pelas ferramentas de arquivo e pelo shell (escopo, seção 0) | testes dos hooks nos dois sistemas; a rodada 4 fechou HOOK-F3, F4, F5, F7 e F8 com contraprova | ajudou |
| M4 | `fundacao-ia-multiprojetos/assets/fundacao-kit/fundacao/core/aberturas.py`, `cli_aberturas.py`, `assets/host/fundacao_titular.py` | ficha de aberturas `fundacao.ficha_aberturas/1`, fechada por padrão e assinada no namespace `fundacao-abertura`; ferramenta do titular em cópia protegida | internet, sites e plugins abertos sem decisão do titular por projeto | testes do kit (805 nos dois sistemas na junção da rodada 2); nenhuma ficha assinada nesta versão | sem efeito observado |
| M5 | `fundacao-ia-multiprojetos/scripts/plugin_candidato.py` e `core/aberturas_markdown.py` | plugin candidato montado, conferido e revisado; o validador do kit é a regra do caminho confiável, e a sessão pode ser mais estrita, nunca mais frouxa | skills e plugins vindos das origens dos projetos | teste de implicação entre as duas regras; a revisão da rodada 2 achou a menção `@` dentro de aspas, corrigida | ajudou |
| M6 | `fundacao-ia-multiprojetos/scripts/ensaio_isolamento_wsl.py` | canário: fundação de mentira, sessões curtas e relatório que o portão confere | o sandbox do Claude Code não confinou comandos com a raiz no disco E: visto pelo Ubuntu (sondas de 31/10/2026) | testes do ensaio; o canário real não rodou nesta versão; a passada de segurança achou CAN-1 a CAN-3, abertos | sem efeito observado |
| M7 | `fundacao-ia-multiprojetos/scripts/importar.py`, `perfil_execucao.py`, `execucao_isolada.py`, `git_projeto.py`, `versao_em_uso.py`, `navegador.py` | ferramentas do fluxo B: importar com plano e cópia, perfil de execução, Git do projeto, versão em uso e navegador da sessão | projetos que funcionam na fundação, com as origens como histórico (respostas do titular de 31/10/2026) | testes dos scripts nos dois sistemas; a rodada 4 fechou FLUXB-F1 (sudo sobre programa da sessão) e FLUXB-F3, KIT-F1 e KIT-F5 | ajudou |
| M8 | `fundacao-ia-multiprojetos/assets/fundacao-kit/fundacao/core/backup.py`, `core/manutencao.py` e `scripts/atualizar_fundacao.py` | política de backup com `em-uso/` e `.claude/projetos/`, `.cache` fora; recusa de destino dentro da raiz e de nome parecido com `state` | cópias sem a versão em uso e com cache (escopo 0.15) | testes do kit e dos scripts; a rodada 4 fechou KIT-F2, F3, F4, F6 e F7 com contraprova | ajudou |
| M9 | `fundacao-ia-multiprojetos/assets/host/windows/preparar-maquina.ps1` e `preparar-projeto.ps1` | `-Backups`, `-BackupsAusente` ou `-SemBackups` obrigatório; perfil do Windows soma as origens registradas; âncora com `fundacao-copia` | o perfil refeito perdia a negação das cópias e das origens; o livro assinado não conferia (I21 a I22) | testes com o PowerShell real em simulação e sonda do `ssh-keygen`; o passo real com UAC é do titular | ajudou |
| M10 | `fundacao-ia-multiprojetos/evals/rastro_do_executor.py` e `entrega/verificar_pacote.py` | awk e sed com execução ou gravação voltam à regra da 1.7.9; `--lista-so-cresce` vê commit descartado num merge | CI-F7 e CI-F8 da revisão de segurança | testes com os casos dos achados | ajudou |
| M11 | `fundacao-ia-multiprojetos/references/` e `assets/templates/` | texto honesto sobre a raiz no disco E: visto pelo Ubuntu, camadas da 1.7.10, plugins, atualização para a 1.7.10, checklist por projeto, roteiro do corte | os textos prometiam o que o código não fazia (consolidação da 1.7.9) | três fases do texto com revisão independente; orçamento do SKILL.md mantido | ajudou |
| M12 | `projects/fundacao-de-ia/ferramentas-liberacao/liberar.py` (fora desta árvore) | `reconferir`, reaproveitamento da etapa 01, WSL conferido antes das etapas 06 e 08, conferidor da revisão no `checar` | a liberação da 1.7.9 rodou três vezes e terminou numa reconferência editada à mão | testes das ferramentas; uso real nesta liberação | sem efeito observado |

## O que a versão traz

- Cada projeto ganha perfil, lançador, área do titular e porteiro próprios no Ubuntu. A sessão de um projeto pede dados
  ao serviço com a identidade `sessao-<p>`, travada no projeto dela.
- Hooks novos nas ferramentas de arquivo, na rede e nas ferramentas do Claude Code, e o aviso semanal de cópia.
- Ficha de aberturas fechada por padrão: internet, sites e plugins por projeto, só com a assinatura do titular e
  depois do canário.
- Plugin candidato com uma regra única de conteúdo, a do validador do kit.
- Ferramentas para trazer cada projeto de verdade para a fundação: importar, perfil de execução, Git do projeto,
  versão em uso e navegador da sessão.
- Cópia de segurança com a versão em uso e as configurações por projeto.
- Preparo do Windows que não perde as negações das cópias nem das origens registradas.
- Revisão de segurança da versão com 34 achados confirmados. A rodada 4 corrigiu os do lote A, com teste que
  reproduz e dupla revisão.

## Estado da liberação e limites conhecidos

O titular pediu, em 01/11/2026, para finalizar com o que havia, publicar e instalar, e levar o resto para a 1.7.11.
A liberação exige suítes e conferências verdes nos dois sistemas, a revisão de segurança, a CI pública verde e os
três destinos conferidos.

Limites que seguem nesta versão:
- **Isolamento lógico.** Com a raiz no disco E: visto pelo Ubuntu, o isolamento entre projetos no Ubuntu é lógico até o canário passar
  no computador do titular. Até lá, uma sessão do Ubuntu também alcança `<raiz>/.claude`, o perfil e os hooks das
  sessões do Windows (HOOK-F1).
- **Achados abertos.**
  - WSL-01, WSL-02 e CAN-2 (médios), a parte do código do CI-F1 (médio; o texto entrou nesta versão) e os baixos do
    lote B ficam para a 1.7.11.
  - As correções estão escritas e sem revisão nos ramos `v1710/seg-perfis`, `v1710/seg-canario` e `v1710/seg-fluxb`.
  - Até lá, o titular fecha o Ubuntu antes do `preparar-wsl.sh` (WSL-02). Ele também roda o canário pelo programa da
    skill instalada e passa ao preparo só o relatório que esse ensaio gravou (CAN-1 e CAN-2).
- **Áreas sem passada dedicada.** O preparo do Windows e os plugins e aberturas não passaram pela passada de segurança
  dedicada: tiveram as revisões dos pacotes e das rodadas de integração.
- **Canário e aberturas.** O canário real não rodou, e nenhuma ficha de aberturas foi assinada.
- **Diferença de regra entre os sistemas.** O kit do Windows não confere o conteúdo executável de um plugin; o do
  Ubuntu e a sessão conferem. A falha é fechada no instalador do Ubuntu.
- **Para a 1.7.11.** A lista fica em `outputs/inicio-1.7.10/lote-3/PENDENCIAS-COORDENADOR.md` do projeto
  fundacao-de-ia. Ali estão o perfil protegido do Windows, a cópia cifrada (o disco D: é externo), a menção `@`
  desligada pelo lançador e os itens do canário que faltam.

## Lições

### L1 — Medir o sandbox no sistema de arquivos real antes de prometer isolamento
- Gatilho: a versão promete separação entre projetos pelo sandbox do host, e a raiz fica num disco montado de outro sistema (DrvFs).
- Lição: sonde o sandbox na pasta real da raiz antes de escrever a promessa; até o ensaio passar no ambiente do titular, chame o isolamento de lógico em todo texto e meça cada achado com a condição do sandbox.
- Evidência: M6, M11; `fundacao-ia-multiprojetos/references/seguranca-isolamento.md` §8.1; as sondas de 31/10/2026 (com a raiz no disco E: visto pelo Ubuntu, o sandbox não confinou; no ext4, confinou); os achados R1710-POR-01 a 03 da revisão de segurança, todos condicionais ao sandbox.
- Confiança: alta

### L2 — Correção que entra depois da passada de segurança precisa de revisão própria
- Gatilho: a revisão de segurança roda sobre um commit e as correções seguintes mudam centenas de linhas do código revisado.
- Lição: reserve no plano, antes de começar, a passada sobre a diferença e as áreas adiadas; correção grande sem revisão fica fora da versão, num ramo, até ser revisada.
- Evidência: M2, M3, M9; `fundacao-ia-multiprojetos/assets/host/windows/preparar-maquina.ps1`; a última correção da rodada 3 da integração (918 linhas) entrou sem nova revisão; o lote B da rodada 4 saiu da versão sem revisão; as áreas do Windows e dos plugins ficaram sem a passada dedicada.
- Confiança: média

### L3 — Fixar o teto de custo de cada fase antes de lançar os agentes
- Gatilho: uma versão com muitos pacotes, rodadas de integração e revisões com céticos independentes por achado.
- Lição: estime o custo de cada fase pelo que a anterior gastou e combine o teto com o titular antes; deixe margem para a revisão da diferença, o relatório e a liberação.
- Evidência: M1 a M12 e `fundacao-ia-multiprojetos/references/atualizacao-1.7.10.md`; o titular pediu para finalizar ao chegar a quase 65% da cota semanal (01/11/2026); a primeira passada de segurança usou 59 agentes.
- Confiança: alta
