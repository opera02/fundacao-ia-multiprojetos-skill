# Kit 1.7.10 sem migração: compatibilidade, ordem e retorno

Escrito em 01/11/2026, antes da aplicação na fundação em uso: o `aplicar` e os preparos do host (com UAC e `sudo`)
só rodaram em testes e ensaios; o resultado real deles e o do canário vão para a RETOMADA quando rodarem. Skill e kit
vão para 1.7.10; o banco fica em `user_version` 5, o mesmo da 1.7.9 (versão da skill, versão do kit e `user_version`
continuam medidas distintas). O que muda está no host — perfil, lançador e porteiro por projeto no Ubuntu, hooks
novos, ficha de aberturas — e na cópia de segurança. A atualização em si é o C6 de
[fluxo-c-operar.md](fluxo-c-operar.md).

Honestidade (registre sempre): nas sondas de 31/10/2026, com a raiz em `/mnt/e`, o sandbox do Claude Code 2.1.302 não
confinou os comandos da sessão. Até o canário passar no ambiente real, ou até a área de dados ir para o ext4 do WSL
(decisão do titular), o isolamento entre projetos no Ubuntu é lógico: regras, trava de projeto, porteiro e hooks.
Nenhuma abertura vale sem a ficha assinada e o canário aprovado ([segurança e isolamento §8](seguranca-isolamento.md)).

## Compatibilidade

| Recurso | Comportamento |
|---|---|
| Banco | As mesmas cinco migrações da 1.7.9: o `init` do kit novo não muda o esquema. Não há tabela nem coluna nova; o único evento novo, `abertura_preparada`, entra na tabela de sempre. Por isso vale o `desfazer` do C6 (Retorno, abaixo). |
| Assinaturas | Namespace novo, `fundacao-abertura`, só para a ficha de aberturas; as decisões seguem em `fundacao-decisao`, e uma assinatura não serve à outra. A linha do titular na âncora da 1.7.9 só permite `fundacao-decisao`: a ficha não confere até o `preparar-maquina.ps1` (com UAC) trocar a linha pela nova, com a mesma chave e três namespaces: `fundacao-decisao`, `fundacao-abertura` e `fundacao-copia`, o do livro de cópias assinado ([atualizacao-1.7.9.md](atualizacao-1.7.9.md)), que a linha da 1.7.9 também não tinha. A linha de uma 1.7.10 de antes, sem `fundacao-copia`, é trocada do mesmo jeito, no mesmo UAC. A linha nova continua valendo para as decisões. |
| Sessão do Ubuntu | Identidade `sessao-<p>`, com o kit travado no projeto (`FUNDACAO_PROJETO_TRAVADO`): só leitura, escrita e uso em `project:<p>`, derivados da trava, sem linha de ACL no banco. Nada de caso, do comum, de outro projeto nem de administração. Sem a trava, ou com a de outro projeto, tudo é negado. Com a raiz em `/mnt/e`, a trava é camada lógica: quem roda o kit fora do porteiro escolhe as variáveis. No Windows, nada muda. |
| Origens e pastas só de leitura | Na 1.7.9, vinham da linha de comando: o `-SomenteLeitura` do `preparar-maquina.ps1` as punha no perfil único do Ubuntu. Na 1.7.10, vêm do `registry/projetos-host.json`, que só o titular grava (`preparo_host.py registrar-projeto`): o perfil de cada projeto no Ubuntu as tira só dele, e o preparo do Windows nega a edição das de todos os projetos (o `preparar-projeto.ps1` as passa dele ao `preparar-maquina.ps1`, que também as lê de lá quando roda sozinho). Sem o registro, o perfil do projeto no Ubuntu não as lista (Ordem, passo 3). |
| Porteiro | Na sessão do Ubuntu, o `python -m fundacao` sobre a raiz real vira um pedido na fila do porteiro (`assets/host/wsl/porteiro.py`), que roda o kit fora do sandbox. Só a operação `fundacao`; `git-enviar`, `executar` e `rodar` saem com código 2 ("1.7.11"). Na partida, o porteiro exige o kit da raiz em 1.7.10 ou mais nova, travado no projeto; senão, recusa todo pedido. O kit da raiz fica fixado pelo SHA-256: depois de qualquer atualização, o lançador só abre depois de um novo `preparar-wsl.sh`. Com a raiz em `/mnt/e`, um comando da sessão ainda alcança o banco por fora do porteiro (camada lógica). |
| Trava do banco | Abrir o banco, também só para leitura, confere o marcador `state/banco.trava`, que o porteiro grava e renova a cada 30 s. Com o marcador do outro lado, o kit recusa (`E_BANCO_TRAVADO`), e o `checar`, o `aplicar` e o `desfazer` param na etapa `banco`. Marcador velho (mais de 120 s sem renovação) só sai pelo titular, com as sessões do Ubuntu fechadas: `python -m fundacao --raiz <raiz> banco destravar --confirmar`. Os comandos do Windows não gravam marcador. É guarda-corpo contra engano, não barreira. O kit da 1.7.9 não conhece o marcador. |
| Trava de manutenção | `state/manutencao.json` (`motivo`, `pid`, `host`, `desde`): o `aplicar` a grava do começo ao fim, e o `backup criar` do kit novo, durante a cópia; ela sai no fim, também na falha. Enquanto ela existe, o lançador do Ubuntu não abre. Trava que já existe faz o `aplicar` parar na etapa `trava`, sem alterar nada: confira o `pid` e o `host` e, sem manutenção em andamento, apague-a e repita. |
| Cópia de segurança | Pasta `.cache`, em qualquer nível, fica fora da cópia, como `node_modules` e `.venv`: é onde o perfil do Ubuntu põe os caches de ferramenta (`projects/<p>/.cache`), que se refazem. O `aplicar` acrescenta `em-uso` e `.claude/projetos` à lista `incluir` de `registry/backup_policy.json` (cria o arquivo, se faltar), antes da cópia DEPOIS: `em-uso/` tem a versão em uso de cada projeto; `.claude/projetos/`, a caixa de entrada das fichas assinadas, que não se refazem. Política ilegível, fora do formato ou com ligação no caminho fica como está, e o resumo pede o acréscimo à mão. |
| Busca e citação | `conhecimento buscar` (CLI e MCP) recusa projeto arquivado ou inexistente, depois da permissão: `E_NOT_FOUND`, código 2 na CLI. A conferência de citação do kit devolve `valid: false` ("projeto inexistente ou inativo"). Antes, projeto arquivado com leitura ainda respondia. |
| Inventário do ambiente | `scripts/inspecionar_ambiente.py` mantém o esquema `fundacao.inventario_ambiente/1` e as chaves de `sistema`. Muda o formato de `sistema.plataforma`: `Windows-<maior>.<menor>.<build>` no Windows e `<sistema>-<versão>` nos outros (antes, o `platform.platform()`, com sufixos como `-SP0`). `programas.<nome>.caminho` é absoluto ou `null`: programa só na pasta atual sai como ausente. Inventários de datas diferentes mudam de forma sem a máquina mudar. |
| Revisão de segurança (rodada 4) | O `guarda_identidade.py` nega comando recursivo conhecido sobre a raiz ou acima e comando acima de 16 KiB (conteúdo grande vai pela ferramenta Write); o `guarda_leitura.py` nega `/mnt/wslg/` e, no Ubuntu, o filtro do Grep com barra invertida ([§8.2](seguranca-isolamento.md)). O `backup criar` e o `backup restaurar` recusam destino dentro da raiz: cópia guardada ali vai para fora, de preferência em outro disco; o `aplicar` recusa `--backups` dentro da raiz. Política de backup com `State`, `STATE`, `state.` ou `.` passa a recusar a cópia: corrija-a (o `checar` a mostra). O `promover` da versão em uso recusa aceite já usado, e o `conferir` diz o que não confere (`nao_conferido`) (capacidade 11). |
| Marcadores do sandbox na raiz | Os 11 nomes da lista obrigatória do bwrap (`.bashrc`, `.bash_profile`, `.zshrc`, `.zprofile`, `.profile`, `.gitconfig`, `.gitmodules`, `.ripgreprc`, `.mcp.json`, `.vscode`, `.idea`) podem ficar na raiz como arquivos de 0 byte, sobra de comando que morreu no sandbox (achado de 30/10/2026). O passo `host` do `scripts/verificar_fundacao.py` os aceita com aviso; nos de shell e git, conteúdo, pasta ou tipo incomum fazem o passo falhar, e ligação ou vínculo físico, em qualquer um (o `.mcp.json` comum até o teto e as pastas `.vscode` e `.idea` são aviso). A remoção é do titular, pela Lixeira. O lançador de cada projeto apaga os de 0 byte da pasta do projeto antes de abrir e ao sair. |

## Ordem numa fundação em uso

Uma sessão só operando a raiz. Cada passo começa com o anterior concluído e registrado na RETOMADA. Os passos 3 a 7
pedem o titular: o executor prepara os comandos prontos (com simulação antes, onde o script tem) e nunca registra
simulação como execução real.

1. **Antes.** Rode o `checar`, que só lê:

   ```
   python <skill>/scripts/atualizar_fundacao.py checar --raiz <raiz>
   ```

   Fechar o Ubuntu é passo do titular: ele fecha as sessões do Ubuntu e, no PowerShell, roda
   `wsl --terminate <distribuição>` para cada distribuição ligada (a recusa do `aplicar` diz quais; se a mensagem
   sugerir `wsl --shutdown`, ele também serve, rodado pelo titular). O executor nunca roda `wsl --shutdown` nem
   `--terminate`: com o Ubuntu ligado, ele para e pede. O `aplicar` recusa com uma distribuição do WSL ligada,
   porque o banco não abre pelos dois lados. Nenhuma outra sessão gravando na raiz: o que
   aparecer depois do `checar`, ele não vê. Com um marcador do banco deixado pelo Ubuntu, o `checar` para na etapa
   `banco` (Trava do banco, acima).
2. **Cópia ANTES e `aplicar`**, num comando só:

   ```
   python <skill>/scripts/atualizar_fundacao.py aplicar --raiz <raiz> --backups <pasta em outro disco>
   ```

   Em ordem: trava de manutenção; cópia ANTES verificada, feita pelo kit da raiz (de uma cópia conferida por hash);
   ensaio numa cópia restaurada, em pasta nova dentro de `--backups` (ou de `--pasta-ensaio`); promoção; `init` e
   cadeia de eventos; instruções da raiz; política de backup; cópia DEPOIS verificada; registro ancorado; inventário do
   host. A cópia ANTES segue as regras do kit anterior; a DEPOIS já sai com as da 1.7.10 (sem `.cache`, com o `.git`
   dos projetos pela regra da cópia e com as áreas novas da política). A estimativa de tempo sai no início (medida em
   31/10/2026: cerca de 17 min para criar e 12 para verificar uma cópia de 130 mil arquivos, e 27 para restaurar; as
   suítes do ensaio à parte). Se a cópia ANTES falhar na promoção,
   ela é refeita uma vez, com rótulo novo; a sobra da primeira tem os dados da fundação: apague-a pela Lixeira, com o OK
   do titular. Se o `aplicar` parar, a saída diz a etapa e o motivo, e o registro da falha fica em
   `evidence/atualizacoes/`: antes da promoção, o código da raiz não muda; depois dela, o registro fica ancorado, com o
   comando de voltar em `para_voltar`.
3. **Registro das origens (titular, uma vez).** O `registry/projetos-host.json` é novo na 1.7.10. O preparo do
   Ubuntu tira dele as origens e as pastas só de leitura de cada projeto, e o `preparar-projeto.ps1` as passa dele ao
   preparo do Windows: sem o registro, o perfil do projeto no Ubuntu não as lista. Registre antes a origem de cada
   projeto vindo de outra pasta (fluxo B):

   ```
   python <skill>/assets/host/preparo_host.py registrar-projeto --raiz "<raiz>" --projeto <p> --origem "<pasta>"
   ```

   Outra pasta que o projeto só lê vai com `--somente-leitura "<pasta>"`. As pastas que a 1.7.9 recebia em
   `-SomenteLeitura` estão no perfil único do Ubuntu dela, `.claude/settings.wsl.json` (em
   `sandbox.filesystem.denyWrite`, as pastas fora da raiz, salvo a da âncora); o passo 4 guarda esse perfil em
   `.claude/anteriores/`. Detalhes: [fluxo-a-implantar.md](fluxo-a-implantar.md) §Host, passo 2.
4. **Windows, com UAC.** O `assets/host/windows/preparar-maquina.ps1`, primeiro com `-Simular`, e sempre com
   `-Backups` (a pasta das cópias de segurança; com o disco delas desligado, `-BackupsAusente`; sem cópias ainda,
   `-SemBackups`): sem nenhum dos dois, ele recusa com código 2 antes de gravar qualquer coisa e mostra o comando
   pronto, porque refaz inteiro o `.claude/settings.json`, e sem as cópias ele tiraria a negação delas. Depois da
   primeira cópia (`registry/ultima-copia.json`), o `-SemBackups` também recusa, e o comando pronto traz a pasta dela.
   As origens e as pastas só de leitura de todos os projetos de
   `registry/projetos-host.json` ele lê do registro (`-SomenteLeitura` fica para a pasta fora dele). O
   `assets/host/windows/preparar-projeto.ps1` de cada projeto, se usado, vem antes, com o mesmo `-Backups`, que ele
   repassa (e a mesma regra: sem `-Backups` nem `-SemBackups`, recusa). O `aplicar` não copia hooks: é este passo que
   instala os novos em `<raiz>/.claude/hooks/`, gera de novo o `.claude/settings.json`, troca a linha da âncora (os
   namespaces `fundacao-abertura` e `fundacao-copia`, com a mesma chave) e, com um Python instalado para todos os
   usuários, grava a cópia protegida da ferramenta do titular. Comandos e ordem:
   [fluxo-a-implantar.md](fluxo-a-implantar.md) §Host, passos 2 a 4.
5. **Ubuntu.** O `assets/host/wsl/preparar-wsl.sh` com `--raiz`, `--titular` e um `--projeto` para cada projeto, sem
   `sudo` na frente (ele o pede só no que exige). Ele confere antes que os hooks e o kit da raiz são os da skill e tira
   do registro (passo 3) as origens de cada projeto: por isso vem depois dos passos 2 a 4. Grava a área do titular
   (`/etc/fundacao-ia/projetos/<p>/`), o lançador `/usr/local/bin/abrir-fundacao-<p>` e a cópia protegida
   `/usr/local/lib/fundacao-ia/<versão>/`; fixa o Claude Code; desliga o interop no `/etc/wsl.conf` (vale depois de
   `wsl --terminate <distribuição>`, no Windows); e aposenta o lançador único da 1.7.9 (`~/abrir-fundacao.sh`).
   Comando: [fluxo-a-implantar.md](fluxo-a-implantar.md) §Host, passo 5 (com `--perfil-windows` quando a skill não está
   em `/mnt/c/Users/<usuario>/...`, `--claude-versao` e `--claude-sha256`). Antes, o titular fecha o Ubuntu como no passo 1 e
   abre um terminal novo só para o preparo: nenhuma sessão roda durante ele, porque o espelho em
   `<raiz>/.claude/projetos/` é gravado como root.
6. **Canário.** O ensaio do item C de `assets/templates/CHECKLIST-PROJETO.md`. Só com
   `conclusao.confina_comandos: true`, instale o relatório com o mesmo `preparar-wsl.sh` e `--canario`. O canário vem
   antes de qualquer ficha e de dado real numa sessão do Ubuntu: se a escrita fora do projeto vazar em `/mnt/e` (o
   canário mede), um comando da sessão poderia gravar também no perfil do Windows, por `/mnt/c`, algo que rode no
   próximo logon (risco deduzido das sondas, não medido). Com `false` ou `null`, tudo fica fechado, e o isolamento,
   lógico. Desde a 1.7.10.1, esse relatório também se instala, como revogação, e a ficha de um projeto só vale com o
   aceite de risco do titular ([correção 1.7.10.1](atualizacao-1.7.10.1.md)).
7. **Só então, as fichas.** A sessão prepara a ficha:

   ```
   python -m fundacao abertura preparar --projeto <p> --rascunho <arquivo>
   ```

   O titular assina pelo comando fixo que o preparo mostra, pela caixa Executar, e roda de novo o `preparar-wsl.sh`
   do projeto, que instala a ficha na área root. Sem o canário aprovado, a ficha não é aplicada.

## Retorno

Como o `user_version` não muda, vale o `desfazer` do C6:

```
python <skill>/scripts/atualizar_fundacao.py desfazer --registro <registro em evidence/atualizacoes/>
```

O resumo do `aplicar` traz esse comando pronto, com o caminho do registro. Ele exige o registro ancorado em
`registry/atualizacoes.jsonl`, o código ainda igual ao que a atualização deixou e nenhum marcador do banco do outro
lado.

**O que volta:** os arquivos de código substituídos (guardados em `registry/kit_backup/`) e os retirados pela
atualização; os criados por ela saem; as instruções da raiz (`AGENTS.md` e `CLAUDE.md`) voltam, salvo as editadas
depois. A volta é anotada em `registry/kit_install.json`. O banco não é tocado.

**O que não volta:**
- A política de backup ampliada: ela só acrescenta, e o kit anterior também a lê (pasta que não existe é pulada). Com o
  kit da 1.7.9 de volta, as cópias voltam a levar as pastas `.cache` e a deixar fora o `.git` dos projetos.
- O que o preparo do host gravou, dentro e fora da raiz. No Windows: a linha nova da âncora e a cópia protegida em
  `C:\ProgramData\FundacaoIA\ferramentas\<versão>\`. Na raiz: os hooks de `.claude/hooks/` e os perfis de `.claude/`
  (os anteriores, inclusive o perfil único do Ubuntu da 1.7.9, ficam em `.claude/anteriores/`). No Ubuntu: a área
  `/etc/fundacao-ia/`, os lançadores por projeto, a cópia `/usr/local/lib/fundacao-ia/<versão>/`, o `/etc/wsl.conf`
  (o anterior fica ao lado), os pacotes, o Claude Code fixado e o lançador único da 1.7.9 aposentado (a cópia dele
  fica ao lado).
- Com o kit anterior na raiz, os lançadores da 1.7.10 não abrem (o kit mudou desde o preparo, e o porteiro exige o kit
  1.7.10): as sessões do Ubuntu ficam fechadas. Trazer de volta o fluxo do Ubuntu da 1.7.9 é decisão do titular.
- O `aviso_copia.py` do Windows lê só o `registry/ultima-copia.json`, que o kit da 1.7.9 não atualiza: passados 7
  dias, ele lembra a cópia mesmo com cópias novas.
- Fichas assinadas, relatório do canário, decisões e eventos ficam como dados.

Se o `desfazer` disser que o `user_version` mudou, não foi a 1.7.10 que o mudou: pare, não use
`--aceitar-banco-migrado` e siga o C9 (a cópia ANTES restaurada em pasta nova). Registro ausente, alterado ou que não
confere com a âncora também leva ao C9.

## Limites conhecidos (registre sempre)

- **Isolamento lógico com a raiz em `/mnt/e`** (início deste texto). O que protege mesmo sem confinamento: os arquivos
  de dono root no Ubuntu, a âncora com ACL de administrador no Windows e as assinaturas do titular — e só enquanto a
  escrita fora do projeto não chegar à pasta do Windows do titular por `/mnt/c` (risco de persistência no próximo
  logon: [segurança e isolamento §8.1](seguranca-isolamento.md)).
- **E10, sujeito de `decisao_preparada`.** Quando a sessão do Ubuntu prepara uma decisão pelo porteiro, a mesma
  identidade autoriza, assina e registra: o titular da configuração do porteiro (`FUNDACAO_ASSINANTE`). O evento sai
  com o titular como sujeito, não com `sessao-<p>`. Separar quem prepara de quem assina fica para a 1.7.11
  (`assets/fundacao-kit/fundacao/core/decisoes.py` está no teto de 741 linhas).
- **Python por usuário no Windows.** A cópia protegida do Windows só registra um Python instalado para todos os
  usuários. Com o Python por usuário, a forma do Windows de assinar a ficha fica pendente, com o motivo no relatório do
  `preparar-maquina.ps1`, e vale a do Ubuntu (`executar_ubuntu`, pelo `wsl.exe`, com a cópia do `preparar-wsl.sh`).
  Para ter a do Windows: instale o Python para todos os usuários e rode o `preparar-maquina.ps1` de novo.
- **`-AssinarFicha` e o perfil do PowerShell.** O `preparar-projeto.ps1 -AssinarFicha` roda a ferramenta dentro do
  PowerShell do script, e os exemplos dele não usam `-NoProfile`: o perfil (`$PROFILE`), que uma sessão pode ter
  gravado, roda antes. É o mesmo risco da forma `powershell`. Prefira o comando fixo pela caixa Executar
  (`executar_windows` ou `executar_ubuntu`).
- **Abertos nesta versão, guardados para a 1.7.11** (o lote B da revisão de segurança, nos ramos `v1710/seg-perfis`,
  `v1710/seg-canario` e `v1710/seg-fluxb`): o preparo e o canário ainda aceitam rodar de uma cópia em `projects/`, o
  canário reprovado não revoga o aprovado e, até o canário passar, uma sessão do Ubuntu alcança `<raiz>/.claude`
  ([§8.4 e §8.5](seguranca-isolamento.md)); os passos do titular seguem a forma fixa dos modelos.
- **`abertura verificar` com `valida: false` sai com código 0**, como o `abertura vigente`. Leia o campo `valida`, não
  o código de saída.
- **Livro assinado da 1.7.9.** A linha da âncora que o preparo da 1.7.9 gravava (só `fundacao-decisao`), e a de uma
  1.7.10 de antes (com `fundacao-abertura`), não permitem `fundacao-copia`, o namespace do livro de cópias assinado
  ([atualizacao-1.7.9.md](atualizacao-1.7.9.md)). O OpenSSH recusa a assinatura feita num namespace fora da lista
  (conferido em 01/11/2026 com uma chave fictícia, no OpenSSH do Windows e no do Git para Windows). O
  `preparar-maquina.ps1` da 1.7.10 grava a linha com os três namespaces e troca a velha, com a mesma chave, no UAC da
  âncora: até o titular rodá-lo com o UAC, a adoção do livro assinado não confere.

## O que fica para a 1.7.11

Do reescopo de 31/10/2026. Cada item é saída de dados ou execução fora do sandbox, cujo confinamento em `/mnt/e` não
se confirmou:
- jaula (bubblewrap e proxy de lista) para MCP de terceiros, como o Playwright; até lá, a seção `mcp` da ficha fica
  reservada, e o `mcp.json` do projeto, vazio;
- navegador com janela e os logins do titular: nesta versão, o `navegador.py abrir --com-janela` recusa (código 2).
  Sem janela, quem usa o navegador é a sessão, no sandbox dela, e é ela que instala o Playwright e o Chromium em
  `projects/<p>/.navegador/`. O único passo do titular é o `sudo apt-get install -y <pacotes>` da lista fixa que o
  próprio `navegador.py` imprime (Ubuntu 24.04). Nenhum passo do titular, com `sudo` ou sem, roda programa de
  `projects/`. O `conferir-perfil-chrome` só lê o `Local State` do perfil copiado e não abre janela;
- Codex interativo por projeto, com jaula;
- porteiro com `git-enviar`, `executar` (segredos) e `rodar`, e a publicação;
- cópia de segurança cifrada (decisão D-CIFRA, com o titular);
- máscara de segredo do sandbox (HTTP; `tlsTerminate` experimental).

Também ficam para a 1.7.11, pelos contratos da versão: o parâmetro `assinante=` (limite E10); `eventos` e
`memoria licao historico` no porteiro, só com leitura restrita ao projeto; as outras seções reservadas da ficha
(`navegador`, `git`, `segredos`, `outras_llm`, `execucao`, `leitura_liberada`, `perfil_navegador_copiado`); plugin com
hooks, MCP ou executável; e o lançador fixo da cerimônia do titular (`/usr/local/bin/fundacao-titular`).
