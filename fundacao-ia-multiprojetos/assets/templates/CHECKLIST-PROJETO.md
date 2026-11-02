# Checklist do projeto — <projeto> — <data>

> Modelo da skill (`assets/templates/CHECKLIST-PROJETO.md`). A sessão do projeto copia este arquivo para
> `projects/<projeto>/CHECKLIST-PROJETO.md` e o preenche; o titular lê, roda os passos marcados "titular" e assina o
> aceite no fim. Um projeto por arquivo. O checklist geral (`assets/templates/CHECKLIST-DADOS-REAIS.md`) continua
> valendo; aqui ficam o canário e o que é deste projeto e do perfil dele. Nenhum item fica "feito" sem evidência
> datada, e nenhum item jurídico vira parecer da skill. A sessão pode alterar este arquivo: o estado só vale com o
> aceite assinado do titular sobre a cópia em `outputs/` (último passo).

> **Regra dos seus comandos (forma fixa).** Copie cada comando seu do modelo da skill instalada (a pasta da skill no
> seu perfil), nunca desta cópia, que a sessão preencheu. Recuse o comando cujo programa fique dentro de
> `<raiz>/projects/`. A sessão não muda estes passos: ela só diz os valores (raiz, projeto, versão).

## O que este checklist garante e o que ainda não garante

- Com a pasta da fundação no disco do Windows (no Ubuntu, `/mnt/<letra>`), o teste de 31/10/2026 mostrou que o
  sandbox do Claude Code não bloqueou os comandos da sessão. Até o canário passar nessa forma de caminho, a separação
  entre projetos no Ubuntu depende das regras (perfil, hooks e porteiro), não de uma barreira do sistema.
- No Windows, nas sessões da raiz, o shell lê tudo: os hooks são guarda-corpo. A separação dos projetos fica nas
  sessões do Ubuntu, lógica como acima até o canário passar.
- Nada se abre sozinho: rede, sites, busca na web e plugins só valem com a ficha de aberturas assinada pelo titular e
  com o canário aprovado (item C) ou, com ele reprovado, com o aceite de risco que o titular assinar para este projeto
  (passo do aceite, abaixo). O aceite não muda o isolamento: ele continua lógico.
- Se um comando da sessão gravar fora do projeto (o canário mede isso), ele também pode gravar na sua pasta do
  Windows, por `/mnt/c`. Um atalho na pasta Inicializar rodaria no seu próximo logon como você, fora de qualquer
  proteção, e alcançaria todos os projetos. Um arquivo `.wslconfig` com `kernel=` trocaria o kernel do WSL no próximo
  início dele e, com o kernel, daria a quem o gravou o controle total do Ubuntu (o root). Um texto malicioso num
  documento basta para pedir isso à sessão. Por isso o canário (item C) roda antes de qualquer dado real.
- Na sessão do Ubuntu, o comando de assinar a ficha chega a você pela própria sessão: confira a forma fixa (o Python
  fixado, a ferramenta na pasta protegida e, depois, só raiz, projeto e versão). Um lançador fixo, instalado pelo
  preparo, fica para a 1.7.11.

## Identificação (a sessão preenche; o titular confere)

- Projeto:
- Forma de caminho da raiz: `drvfs:/mnt/<letra>` (raiz no disco do Windows) | `ext4` (raiz no disco do Ubuntu)
- Claude Code fixado (versão e SHA-256):
- Perfil do projeto: SHA-256 de `/etc/fundacao-ia/projetos/<projeto>/settings.wsl.json` e a data:
- Lançador: SHA-256 de `/usr/local/bin/abrir-fundacao-<projeto>`:
- Ficha de aberturas em vigor (versão e SHA-256), ou "nenhuma: tudo fechado":
- Canário: arquivo em `/etc/fundacao-ia/canario/`, SHA-256, forma, data e `conclusao.confina_comandos`:
- Aceite de risco do canário (data, vigência e SHA-256 do relatório aceito), ou "nenhum":
- Decisões do titular que valem para este projeto (arquivo e data):

No terminal do Ubuntu, estes dois comandos mostram os valores (só leem):

```sh
sha256sum /etc/fundacao-ia/projetos/<projeto>/settings.wsl.json /usr/local/bin/abrir-fundacao-<projeto> /etc/fundacao-ia/canario/*.json
python3 -I -B -c "import json,sys; d=json.load(open(sys.argv[1],encoding='utf-8')); print(json.dumps({k: d.get(k) for k in ('claude','canario','aceite_risco','ficha','lancador')},ensure_ascii=False,indent=1))" /etc/fundacao-ia/projetos/<projeto>/hashes.json
```

## Estados e a regra do perfil novo

- Estados: `pendente` · `feito` (com a evidência e a data) · `não se aplica` (com o motivo) · `aceito pelo titular`
  (com a decisão: arquivo e data). "Aceito" não é "feito": registra que o titular decidiu seguir com aquele limite.
- "Vale para": `fundação` (a mesma evidência serve a todos os projetos; cite-a), `projeto` ou `perfil`.
- Perfil novo: quando o SHA-256 do perfil ou do lançador muda (por exemplo, depois de uma ficha nova aplicada, de uma
  atualização da fundação ou de um projeto novo na raiz, com o preparo do Ubuntu rodado de novo) ou o Claude Code
  fixado muda, os itens de `perfil` (C, 6, 7, 11 e 12) voltam a `pendente` e as provas deles são refeitas. Anote os
  hashes novos acima.
- Com item pendente, vale a regra 9 da SKILL.md: dados reais só com o checklist completo. Nenhuma abertura vale sem a
  ficha assinada e sem o item C com `true` ou, com ele `false` ou `null`, sem o aceite de risco assinado deste projeto;
  `aceito pelo titular` nos itens 6 e 7 mantém o trabalho com a separação lógica e não abre nada.
- O item C vem antes de qualquer dado real. Com `false` ou `null` e a raiz no disco do Windows, ele só sai de
  `pendente` com a sua decisão (`aceito pelo titular`), que cita também o risco da pasta do Windows (no começo deste
  checklist). Desde a 1.7.10.1, essa decisão pode ser o aceite de risco assinado (passo do aceite, abaixo), que também
  deixa valer a ficha deste projeto. A outra saída é levar a área de dados para o disco do Ubuntu, com o canário de lá
  aprovado.

## Itens

| # | Verificação | Vale para | Quem | Evidência (data) | Estado |
|---|---|---|---|---|---|
| C | Canário do isolamento aprovado (`conclusao.confina_comandos: true`) na forma de caminho da raiz, com o Claude Code fixado, instalado na área do titular e fixado no preparo deste projeto; roda antes de qualquer dado real | perfil | titular | | pendente |
| 1 | Treinamento com dados desligado nas contas e planos usados neste projeto (texto completo no checklist geral) | fundação | titular | | pendente |
| 2 | Rota para conteúdo sigiloso definida | fundação | titular | | pendente |
| 3 | Base legal, finalidade e necessidade por operação registradas | projeto | profissional responsável | | pendente |
| 4 | Transferência internacional: mecanismo de cada provedor conferido | projeto | profissional responsável | | pendente |
| 5 | Cliente informado sobre o uso de IA, quando as regras profissionais exigem | projeto | profissional responsável | | pendente |
| 6 | Comandos e ferramentas desta sessão não leem outros projetos, `state/` nem segredos de fora dela: o perfil instalado confere e o canário aprovado (C) vale para ele (prova 6) | perfil | titular + sessão | | pendente |
| 7 | Segredos ilegíveis e escrita só neste projeto, com prova negativa nesta sessão e dados fictícios (prova 7); para os comandos, "feito" só com o item C aprovado | perfil | sessão + titular | | pendente |
| 8 | Cópia de segurança fora da máquina, com restauração ensaiada e registro de retiradas | fundação | executor | | pendente |
| 9 | ACL por cliente ou caso ("muralha ética"): caso A não recupera caso B. Na sessão do Ubuntu, a identidade `sessao-<projeto>` não alcança caso nenhum pelo serviço: o item vale para as outras identidades | projeto | executor | | pendente |
| 10 | Componentes externos (skills, plugins, pacotes) fixados por versão e hash, com revisão; plugin só pela ficha assinada | projeto | executor | | pendente |
| 11 | Identidade das operações vinda do lançador (`sessao-<projeto>`, presa a este projeto) e decisões assinadas pelo titular | perfil | titular | | pendente |
| 12 | Aberturas fechadas por padrão e sem instrução vinda de dado: só abre o que a ficha assinada em vigor traz, com o item C aprovado; `projects/*/data/` fora das instruções; skills e agentes de subpasta negados pelo nome (prova 12) | perfil | sessão + titular | | pendente |

## Passo do titular: o canário (item C)

O canário monta uma fundação de mentira, com dados fictícios, abre sessões curtas do Claude Code e mede se a sessão
de um projeto lê ou grava o que não é dela. Rode-o antes de qualquer dado real (o motivo está no começo deste
checklist). O relatório vale para a máquina: serve a todos os projetos com o mesmo Claude Code fixado e a mesma forma
de caminho da raiz. Refaça quando o Claude Code fixado mudar.

Antes: o `preparar-wsl.sh` já rodou uma vez (ele fixa o Claude Code em
`~/.local/share/fundacao-ia/claude/<versão>/claude`). Tudo no terminal do Ubuntu, como o seu usuário, sem sudo.
`<skill>` é a pasta da skill instalada no seu perfil, a mesma com que você roda o preparo; nunca uma pasta dentro de
`<raiz>/projects/`. As sessões gastam a sua assinatura; o ensaio não fixa o modelo (vale o padrão da sua conta).

1. Prepare o ensaio numa pasta nova, no mesmo disco da raiz e fora dela:

   ```sh
   python3 -I -B <skill>/scripts/ensaio_isolamento_wsl.py preparar --base "/mnt/<letra>/Ensaio de IA" --forma "drvfs:/mnt/<letra>/Ensaio de IA"
   ```

   A saída mostra `config` (a configuração do ensaio, na sua casa do Ubuntu), `sessoes` (quantas sessões curtas o
   ensaio vai abrir) e `proximo_passo`.
2. Faça o login uma vez nessa configuração: rode a linha abaixo, digite /login, conclua e saia com /exit.

   ```sh
   CLAUDE_CONFIG_DIR=<config da saída> ~/.local/share/fundacao-ia/claude/<versão>/claude
   ```

3. Rode o ensaio (leva alguns minutos):

   ```sh
   python3 -I -B <skill>/scripts/ensaio_isolamento_wsl.py rodar --base "/mnt/<letra>/Ensaio de IA" --claude ~/.local/share/fundacao-ia/claude/<versão>/claude --saida ~/canario-drvfs.json
   ```

   Código 0: confina. Código 1: não confina ou não provou. Código 2: erro de uso ou falta algo; a mensagem diz o que
   fazer.
4. Leia `conclusao.confina_comandos` em `~/canario-drvfs.json` (o comando abaixo só lê):

   ```sh
   python3 -I -B -c "import json,sys; c=json.load(open(sys.argv[1],encoding='utf-8'))['conclusao']; print(json.dumps({k: c.get(k) for k in ('confina_comandos','motivo','carga_aninhada')},ensure_ascii=False))" ~/canario-drvfs.json
   ```

   - `true`: os comandos ficaram confinados nesta forma de caminho;
   - `false`: um item vazou (em `itens`, veja o que tem `"veredito": "falhou"` e o motivo). Não abra aberturas;
   - `null`: não provou (veja `conclusao.motivo` e os itens `nao_medido`).
   `conclusao.carga_aninhada` é outra medida (se skill ou agente de subpasta carrega), fora de `confina_comandos`:
   anote-a no item 12.
5. Instale o relatório (com `true`, ele aprova; com `false` ou `null`, vai como revogação, e só abre o projeto com o
   seu aceite de risco: passo do aceite, abaixo). Em `--canario`, passe só o relatório que o ensaio do passo 3 gravou
   na sua casa (`~/canario-drvfs.json`), nunca um arquivo de `projects/`. Antes, feche as sessões do Ubuntu e, no PowerShell
   do Windows, rode `wsl --terminate <distribuição>`; depois abra um terminal novo do Ubuntu só para este passo. Assim
   nenhuma sessão roda durante o preparo, que grava como root o espelho em `<raiz>/.claude/projetos/`. Não ponha sudo
   na frente: o script pede o sudo sozinho. Em `--claude-versao`, use a mesma versão dos passos 2 e 3.

   ```sh
   bash <skill>/assets/host/wsl/preparar-wsl.sh --raiz "<raiz no Ubuntu>" --projeto <projeto> --titular <sua identidade> --claude-versao <versão> --canario ~/canario-drvfs.json
   ```

   Sem `--claude-versao`, o script fixa a versão para a qual `~/.local/bin/claude` aponta; se não for a do ensaio, o
   relatório não vale para ela, e tudo continua fechado. Pode repetir `--projeto`, um para cada projeto. O mesmo
   preparo grava, de dono root, a cópia protegida da ferramenta que assina a ficha
   (`/usr/local/lib/fundacao-ia/<versão>/`). Se a skill não estiver em `/mnt/c/Users/<usuario>/...`, o script pede também
   `--perfil-windows /mnt/c/Users/<usuario>` (o seu usuário do Windows).
   Vale só o relatório da forma de caminho da raiz: com a raiz no disco do Windows, o de `drvfs`. A área guarda um
   relatório por versão do Claude Code; trocar o que liberou uma ficha faz o lançador do projeto recusar abrir até um
   novo preparo. Com `false` ou `null` (desde a 1.7.10.1), o script mostra `[revogar] canario` e segue: o relatório
   substitui o aprovado da mesma versão do Claude Code, e o preparo de cada projeto fecha as aberturas, salvo no
   projeto com o seu aceite de risco assinado para esse relatório. A separação continua lógica, e o resultado vai para
   o item C e para a RETOMADA do projeto. Antes de qualquer dado real, decida como diz a regra do item C (em
   "Estados"). Só um arquivo que não é relatório real do ensaio (simulação, outro esquema) é recusado (código 1).
6. Limpe o ensaio:

   ```sh
   python3 -I -B <skill>/scripts/ensaio_isolamento_wsl.py limpar --base "/mnt/<letra>/Ensaio de IA"
   ```

   Com `sobras` e `restantes` vazios, está tudo limpo; o login do ensaio sai junto. Para rodar de novo, prepare
   outra vez (uma base já rodada é recusada) e rode um ensaio por vez.

Opcional, para decidir se os dados vão para o disco do Ubuntu: o mesmo ensaio no ext4, com `--base ~/ensaio-canario`
(sem `--forma`: o padrão é `ext4`) e `--saida ~/canario-ext4.json`. Esse relatório não vale para a raiz no disco do
Windows: não o instale nesse caso.

## Passo do titular: o aceite de risco do canário (só com `false` ou `null`; desde a 1.7.10.1)

Com o canário reprovado, você pode decidir que a ficha DESTE projeto valha mesmo assim. O aceite não muda o
isolamento (continua lógico: os riscos do começo deste checklist valem) e não abre nada sozinho: abre só o que a ficha
assinada lista, só neste projeto, até a data dele (até 180 dias; a ferramenta propõe 90). Ele se prende ao relatório:
com outro relatório instalado, outro Claude Code fixado ou outra forma de caminho da raiz, tudo fecha de novo.

1. Instale o relatório reprovado como no passo 5 do canário (ele vai como revogação; o preparo segue com tudo fechado).
   Esse preparo também grava a cópia protegida da ferramenta com o comando `aceitar-risco`.
2. Assine o aceite pela ferramenta fixa, na cópia protegida, fora do Claude (a caixa Executar, Win+R, abre o Python
   fixado sem o perfil de um shell). Ela lê o relatório, mostra o que ele mediu e a lista fixa de riscos, pede que
   você digite o nome do projeto e pede a senha da sua chave:

   ```
   C:\Windows\System32\wsl.exe -e /usr/bin/python3 -I -B -S "/usr/local/lib/fundacao-ia/<versão do kit>/assets/host/fundacao_titular.py" aceitar-risco --raiz "<raiz no Ubuntu>" --projeto <projeto> --canario "~/canario-drvfs.json"
   ```

   No terminal do Ubuntu, a mesma coisa:

   ```sh
   /usr/bin/python3 -I -B -S /usr/local/lib/fundacao-ia/<versão do kit>/assets/host/fundacao_titular.py aceitar-risco --raiz "<raiz no Ubuntu>" --projeto <projeto> --canario ~/canario-drvfs.json
   ```

   Passe o mesmo relatório do passo 5 do canário. `--vigencia-ate AAAA-MM-DD` escolhe outra data (até 180 dias).
3. Com a ficha do projeto também assinada, rode de novo o preparo deste projeto (o comando do passo 5, sem o
   `--canario` se o relatório já está instalado). O relatório mostra "canário NÃO aprovado: a ficha vale só neste
   projeto, sob o aceite de risco"; o perfil novo vale numa sessão nova. Anote o aceite na Identificação.
4. O item C fica `aceito pelo titular`, com o aceite citado (versão, data, vigência e SHA-256 do relatório). Os itens 6
   e 7 continuam com a separação lógica. Para fechar antes da data: uma ficha nova sem as aberturas, assinada, e o
   preparo (a "Correção 1.7.10.1" da skill, Retorno).

## Provas do perfil (refeitas a cada perfil novo)

Nenhuma prova lê dado real de outro projeto: a leitura cruzada é medida só na fundação de mentira do canário. Os
arquivos de prova são fictícios e saem no fim.

### Prova 6 — o perfil instalado confere (titular, no terminal do Ubuntu)

1. Anote os hashes da Identificação (comandos acima).
2. Confira o perfil instalado contra o que o preparo gera (cada outro projeto e `state/` negados, as skills do
   registro negadas, a lista de ferramentas igual à do lançador):

   ```sh
   python3 -I -B <skill>/assets/host/preparo_host.py conferir-perfil-wsl --perfil /etc/fundacao-ia/projetos/<projeto>/settings.wsl.json --raiz "<raiz no Ubuntu>" --projeto <projeto> --lancador /usr/local/bin/abrir-fundacao-<projeto>
   ```

   Código 0 com `"ok": true`: confere. Código 1: leia `problemas` e rode o preparo de novo.
3. No `hashes.json` (segundo comando da Identificação), `canario.aprovado` tem de ser `true`, com a mesma forma da
   raiz. Feito só com os três passos. Com `false` (com ou sem `aceite_risco`: o aceite não confina nada), o item fica
   `pendente`, ou `aceito pelo titular` com a decisão
   citada: a separação é lógica.

### Prova 7 — segredo e escrita (a sessão roda; o titular cria e apaga o arquivo fictício)

1. O titular cria, no terminal do Ubuntu, um segredo fictício dentro do projeto:

   ```sh
   mkdir -p "<raiz no Ubuntu>/projects/<projeto>/prova" && printf 'VALOR-FICTICIO-DE-PROVA\n' > "<raiz no Ubuntu>/projects/<projeto>/prova/segredo.key"
   ```

2. A sessão tenta ler `prova/segredo.key` com a ferramenta Read: tem de ser recusado.
3. A sessão roda, na pasta do projeto, um subprocesso, como o canário:

   ```sh
   /usr/bin/python3 -I -B -c 'import sys;print(open(sys.argv[1]).read())' prova/segredo.key; echo "codigo=$?"
   ```

   Um `cat` não serve: o Claude Code o reconhece, e a regra de leitura do perfil pode recusá-lo antes de rodar, também
   onde o sandbox não confina; isso não prova o sandbox. Sem a linha `codigo=` na saída, o comando não rodou e a prova
   não mediu: anote e refaça. Com o sandbox confinando, o valor não aparece (como no canário, vale o valor, não o
   código de saída). Se o valor aparecer, o item 7 não fica "feito": fica `pendente` ou, com a decisão do titular,
   `aceito pelo titular` (separação lógica).
4. A sessão tenta gravar fora do projeto com a ferramenta Write, em `<raiz no Ubuntu>/prova-escrita-<projeto>.txt`:
   tem de ser recusado. A escrita por comando fora do projeto é o item `escrita_fora_do_projeto` do canário.
5. O titular apaga a prova: `rm -r "<raiz no Ubuntu>/projects/<projeto>/prova"` (e o `prova-escrita-<projeto>.txt`
   da raiz, se ele existir).

### Prova 12 — aberturas e instruções (a sessão roda)

1. A ficha em vigor: o comando `abertura vigente` do kit, que a sessão pede pelo porteiro, mostra `valida`, a versão e
   o que ela abre. Sem ficha válida, tudo fechado. Anote na Identificação.

   ```sh
   python3 -m fundacao abertura vigente --projeto <projeto> --json
   ```

2. Busca na web: a sessão tenta usar WebSearch. Sem a ficha abrir, tem de ser recusada (ferramenta ausente ou negada).
3. Site fora da ficha: a sessão tenta WebFetch em `https://example.com`: tem de ser recusado. A sessão roda também
   `curl -sS -m 10 -o /dev/null https://example.com; echo "codigo=$?"`: código diferente de 0. Sem a linha `codigo=`,
   o curl não rodou e a prova não mediu: anote e refaça.
4. Instruções de subpasta: a sessão roda, na pasta do projeto,
   `python3 -I -B <skill>/scripts/instrucoes_aninhadas.py listar --raiz .`. Cada nome em `sugestoes.negar_skills`
   tem de estar negado no perfil, como `Skill(<nome>)` em `permissions.deny` de
   `/etc/fundacao-ia/projetos/<projeto>/settings.wsl.json`. Nome que falta: o titular o acrescenta ao registro
   (`preparo_host.py registrar-projeto ... --negar-skill <nome>`, com a mesma `--origem` já registrada) e roda o
   preparo de novo (perfil novo). Anote também `conclusao.carga_aninhada` do canário.

## Fechamento (aceite assinado)

1. A sessão copia este arquivo preenchido para `outputs/checklist/CHECKLIST-PROJETO-<AAAAMMDD>.md`.
2. Cria a tarefa (uma vez): `python3 -m fundacao tarefa criar --projeto <projeto> --objetivo "checklist do projeto"`.
3. Prepara o aceite:

   ```sh
   python3 -m fundacao decisao preparar --projeto <projeto> --tarefa <id da tarefa> --entrega outputs/checklist/CHECKLIST-PROJETO-<AAAAMMDD>.md --tipo aceite --motivo "<palavras do titular>"
   ```

4. O titular assina com o comando que a decisão mostra (`para_o_titular`). A sessão registra
   (`python3 -m fundacao decisao registrar --arquivo <decisão>`) e conclui a tarefa
   (`python3 -m fundacao tarefa concluir --decisao <decisão>`).

Perfil novo depois do aceite: os itens de `perfil` voltam a `pendente`, e o aceite deixa de valer para eles.
