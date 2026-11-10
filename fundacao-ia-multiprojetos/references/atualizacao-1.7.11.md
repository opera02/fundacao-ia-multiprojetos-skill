# Atualização 1.7.11: o que muda para o titular e os passos dele

Escrita em 09/11/2026. A skill e o kit vão para 1.7.11. O kit mudou de versão porque ganhou arquivos (`canario.py`,
cópia cifrada, jaula): por isso os programas que a fundação guarda pelo SHA-256 precisam de um preparo novo. O banco não
muda de esquema. O que mudou, por área e com os commits: `entrega/licoes/MUDANCAS-1.7.11.md` na árvore de
desenvolvimento. Este texto é só o que você precisa saber e fazer.

## O que muda para você

- **O Criador de petições pode abrir mais coisas**, só com uma ficha nova assinada por você: o conector do escritório com
  todas as ferramentas (inclusive as que gravam no servidor dele), um navegador com perfil novo, o Codex pela sua conta
  do ChatGPT (só na janela que você abre; a sessão não o usa) e os sites principais (`stf.jus.br` e semelhantes). Nada abre sem a sua assinatura.
- **As sessões do Ubuntu abrem com o modo sem perguntas disponível.** Ele começa desligado; você o liga com Shift+Tab
  quando quiser. Ligado, a sessão não mostra o comando antes de rodar. As regras de negação e os hooks continuam valendo,
  segundo a documentação lida em 08/11; o canário novo mede isso.
- **As cópias de segurança saem cifradas** assim que a chave da cópia estiver instalada. Só você sabe a senha. Perdeu a
  senha, perdeu a cópia.
- **Skills com scripts e agentes de arquivo** abrem pela ficha, presos por hash.
- **A regra do código enxuto existe, mas vem desligada.** A rodada de teste mostrou diffs menores e nenhuma economia de
  gasto em tarefa pequena.

## Quatro avisos antes de começar

1. **Os perfis de sessão já instalados vão falhar na abertura** (a conferência exige uma negação nova). Isso é esperado:
   o preparo do Ubuntu os refaz. Até lá, o lançador do projeto recusa abrir e mostra o comando. O perfil refeito traz
   `disableSkillShellExecution` e, sem ficha válida, `FUNDACAO_SKILLS` com `-` (nenhuma skill abre); e a abertura passa a
   recusar quando a sessão plantou uma skill ou um agente aninhado depois do preparo (a tela traz o comando de registrar).
2. **A chave da cópia pede um UAC só dela.** Quando o preparo da máquina também pede UAC, você vê dois avisos seguidos.
   Aceite os dois.
3. **O relatório do canário antigo que dizia "aprovado" deixa de aprovar.** O canário tem de rodar de novo (passo 3). O
   relatório reprovado antigo continua valendo sob o seu aceite de risco.
4. **O kit mudou de versão** (1.7.10 para 1.7.11). A sessão da raiz aplica a atualização antes de você e avisa; não rode
   nada abaixo antes desse aviso.

## Passo 0: feche o Ubuntu

Feche as janelas do Ubuntu. No PowerShell comum:

```
wsl --terminate Ubuntu
```

Depois deste passo, só abra o Ubuntu quando o texto mandar.

## Passo 1: reinstale a cópia protegida da ferramenta (Windows, com UAC)

Esta cópia é a que assina a ficha e confere o canário. A da 1.7.10.x continua rodando o código antigo, então ela tem de
ser refeita. No PowerShell comum, primeiro só ensaiando (`-Simular` não grava nada):

```
powershell -ExecutionPolicy Bypass -File "C:\Users\<usuario>\.claude\skills\fundacao-ia-multiprojetos\assets\host\windows\preparar-maquina.ps1" -Raiz "D:\IA\fundacao" -Titular <titular> -Projeto <projeto das sessões do Windows> -Backups "F:\copias" -Simular
```

Se terminar sem erro, rode o mesmo comando sem o `-Simular`. Aceite o UAC. No fim, o relatório diz que a cópia da
ferramenta ficou em `C:\ProgramData\FundacaoIA\ferramentas\1.7.11`.

## Passo 2: prepare a máquina e o Ubuntu

Abra um terminal novo do Ubuntu, como o seu usuário, sem `sudo` na frente. O script pede a sua senha do Linux só no que
exige administrador e diz antes o que é. Repita `--projeto` para cada projeto. Primeiro veja o plano (`--simular` não
altera nada):

```
bash "/mnt/c/Users/<usuario>/.claude/skills/fundacao-ia-multiprojetos/assets/host/wsl/preparar-wsl.sh" --raiz "/mnt/d/IA/fundacao" --projeto <projeto> --titular <titular> --preparar-jaula --simular
```

Com o `--preparar-jaula`, o plano mostra antes o que vai baixar. Confira:

| O que | Tamanho |
|---|---|
| Bibliotecas do Ubuntu para o Chromium (apt) | cerca de 150 MB |
| Playwright 1.64.1 | 48.471.931 bytes |
| pyee 14.0.0 | 15.553 bytes |
| greenlet 3.5.6 | 621.404 bytes |
| typing_extensions 4.16.0 | 45.571 bytes |
| Soma das quatro rodas do Playwright (cada uma com SHA-256 fixado) | 49.154.459 bytes, cerca de 49,2 MB |
| Chromium (revisão 1248) e o headless-shell | estimativa: cerca de 170 MB baixados e 500 MB no disco (o Playwright não publica o tamanho nem o hash; o hash da pasta instalada é registrado na primeira instalação) |
| Codex 0.166.0 (`codex-x86_64-unknown-linux-musl.tar.gz`, SHA-256 conferido antes de instalar) | 121.764.138 bytes, cerca de 116 MiB |

Se estiver de acordo, rode o mesmo comando sem o `--simular`. Se quiser pular o navegador e o Codex, não use
`--preparar-jaula`: eles só são instalados quando a ficha assinada pedir. Quando o relatório mostrar
`aninhadas-fora-do-registro`, ele já traz o comando pronto; rode-o e repita o preparo.

No fim, o script lista os comandos do canário da jaula (um por modo). Guarde essa lista para o passo 3.

## Passo 3: rode o canário novo

O canário é o ensaio que mede se a sessão consegue ler ou gravar o que não é dela. Agora ele tem 25 sessões curtas (24
sem a do filtro seccomp), com medidas novas (M1 a M3 na fundação; M6 e M7 na jaula) e gasta mais da sua assinatura do Claude do que o de antes. No terminal
do Ubuntu:

1. Prepare o ensaio:

   ```
   python3 -I -B "/mnt/c/Users/<usuario>/.claude/skills/fundacao-ia-multiprojetos/scripts/ensaio_isolamento_wsl.py" preparar --base "/mnt/d/Ensaio de IA" --forma "drvfs:/mnt/d/Ensaio de IA"
   ```

2. Faça o login do ensaio uma vez (use a `config` que o passo anterior mostrou; digite `/login`, conclua e saia com
   `/exit`):

   ```
   CLAUDE_CONFIG_DIR=<config mostrada> ~/.local/share/fundacao-ia/claude/<versão>/claude
   ```

3. Rode o ensaio (leva alguns minutos):

   ```
   python3 -I -B "/mnt/c/Users/<usuario>/.claude/skills/fundacao-ia-multiprojetos/scripts/ensaio_isolamento_wsl.py" rodar --base "/mnt/d/Ensaio de IA" --claude ~/.local/share/fundacao-ia/claude/<versão>/claude --saida ~/canario-drvfs.json
   ```

4. Rode, um por vez, os comandos do canário da jaula que o passo 2 listou. Cada um grava um arquivo de resposta.

   Antes de abrir as sessões do Criador, faça as medidas que ainda faltam e que só o seu canário mostra: a M1 (o `sudo`
   dentro da sessão), a M6 (sandbox do Chromium na jaula), a M7 (sandbox do Codex na jaula) e a "jaula-acesso". O
   `FUNDACAO_SKILLS` não depende de medida: o preparo grava `-` ("nenhuma skill"), um valor não vazio, que segue o mesmo
   caminho das outras variáveis do perfil.
5. Volte à sessão da raiz e diga "canário rodou". Ela lê o resultado e diz o que ficou aprovado, reprovado ou sem
   medida. Um canário reprovado não impede nada sozinho: ele pede o seu aceite de risco, como na 1.7.10.1.
6. Limpe o ensaio:

   ```
   python3 -I -B "/mnt/c/Users/<usuario>/.claude/skills/fundacao-ia-multiprojetos/scripts/ensaio_isolamento_wsl.py" limpar --base "/mnt/d/Ensaio de IA"
   ```

## Passo 4: assine a ficha nova do Criador

A sessão do projeto prepara a ficha e mostra o comando pronto para você assinar. Antes, ela precisa de três respostas
suas, e você as dá em uma mensagem:

- **O plano do ChatGPT** que você usa (por exemplo, Plus, Pro ou Business). A resposta de 08/11 disse que o treinamento
  está desligado, mas não disse o plano. A ficha guarda o plano em `r55.plano`, com a data da conferência, que vale 90
  dias (até 06/02/2027).
- **Os sites do navegador** em que você fará login (até 20).
- **Os domínios que faltam** (o curinga já cobre o site principal; o teto é de 200 por seção).

A ficha nova traz: o conector do escritório com todas as ferramentas, **as que gravam num bloco separado na tela**; o
navegador com perfil novo; o Codex pela sua conta; os domínios; e as skills com scripts, se houver. Leia a tela. Digite
o nome do projeto e a senha da sua chave. O comando vem da própria sessão (`para_o_titular`), e você o roda pela caixa
Executar (Win+R), fora do Claude.

Depois de assinar, repita o preparo do Ubuntu deste projeto, agora com o canário e as respostas da jaula:

```
bash "/mnt/c/Users/<usuario>/.claude/skills/fundacao-ia-multiprojetos/assets/host/wsl/preparar-wsl.sh" --raiz "/mnt/d/IA/fundacao" --projeto <projeto> --titular <titular> --claude-versao <versão> --canario ~/canario-drvfs.json --canario-jaula <resposta do modo 1> --canario-jaula <resposta do modo 2>
```

Use um `--canario-jaula` para cada arquivo de resposta do passo 3.4. Se o canário reprovou, assine antes o aceite de risco
(`references/atualizacao-1.7.10.1.md`).

## Passo 5: faça os logins

Só depois do passo 4. Os dois logins são seus, feitos na sua janela; a sessão não vê as senhas.

Cada site do navegador (a tela da ficha mostra o comando de cada um):

```
abrir-navegador-<projeto> login <site>
```

Entre no site, feche a janela. O navegador guarda o login no perfil novo do projeto, que fica só dentro da jaula.
Site de tribunal que usa CAPTCHA: use `abrir-navegador-<projeto> captcha <endereço>` e resolva você mesmo; nada aqui
resolve CAPTCHA.

O Codex, pela conta do ChatGPT (código de dispositivo):

```
abrir-codex-<projeto> --login
```

Siga as instruções na tela. O login fica com um usuário separado do Ubuntu, fora do alcance dos comandos da sessão, e a sessão não pede Codex pela conta
(esse modo fica fechado; usá-lo na sessão exigiria a chave de API do projeto, com teto de gasto, decisão sua). O
terminal do Codex abre depois com `abrir-codex-<projeto>`. Atenção: o que você digitar e os arquivos que ele ler vão à
OpenAI (EUA), e o token alcança a conta inteira do ChatGPT. O que o Codex gravar não volta sozinho ao projeto: ao fechar
a janela, o `abrir-codex-<projeto>` mostra a lista de arquivos e tamanhos e só os traz para `outputs/codex/` se você
apertar `s` no seu terminal; sem isso, a saída fica retida na jaula e você a traz depois com
`abrir-codex-<projeto> --trazer <id>`.

**Aviso sobre o Codex.** A janela do Codex mostra a lista do que vai voltar ao projeto e pede `s`. Leia os nomes antes de
confirmar, porque a confirmação mostra nomes e tamanhos, não o conteúdo. Com a conta do ChatGPT, só você usa o Codex. Se
quiser a sessão usando o Codex, a opção é a chave de API do projeto, com teto de gasto, decisão sua.

## Passo 6: crie a chave da cópia cifrada

A cópia só sai cifrada depois deste passo. Faça com calma, uma vez.

1. No PowerShell comum, crie a chave. Uma janela do gpg pede a senha nova, duas vezes, e uma terceira vez para exportar
   a cópia protegida. Invente seis palavras sem relação entre si. Ajuste o Python para o que está instalado para todos os
   usuários:

   ```
   & "C:\Program Files\Python312\python.exe" -I -B -S "C:\ProgramData\FundacaoIA\ferramentas\1.7.11\assets\host\fundacao_titular.py" preparar-chave-copia --raiz "D:\IA\fundacao" --guardar-em "C:\Users\<usuario>\Documents\chave-da-copia"
   ```

2. **Guarde a senha fora do computador**, no papel, com a impressão digital da chave que a tela mostra. A senha só
   existe na sua cabeça e no papel. Perdida a senha, as cópias não se recuperam.
3. Copie a pasta `chave-da-copia` para um terceiro lugar à parte (pen drive guardado fora, ou a sua nuvem). Sozinha, sem
   a senha, ela não abre nada. Não a guarde no disco das cópias.
4. Instale a chave pública (pede o UAC, que pode ser o segundo da sessão). Use os mesmos `-Raiz`, `-Titular`, `-Projeto`
   e `-Backups` do passo 1 e acrescente `-ChaveDaCopia` com o caminho do arquivo `.asc` que o item 1 deste passo mostrou:

   ```
   powershell -ExecutionPolicy Bypass -File "C:\Users\<usuario>\.claude\skills\fundacao-ia-multiprojetos\assets\host\windows\preparar-maquina.ps1" -Raiz "D:\IA\fundacao" -Titular <titular> -Projeto <projeto das sessões do Windows> -Backups "F:\copias" -ChaveDaCopia "C:\Users\<usuario>\AppData\Local\FundacaoIA\chave-da-copia.asc"
   ```

   Compare a impressão digital da tela com a do seu papel antes de aceitar. Outra chave depois dessa só entra com
   `-TrocarChaveDaCopia` (a anterior fica guardada ao lado).

A partir daí, o `backup criar` cifra sozinho. A sessão da raiz faz a primeira cópia cifrada, verifica e, quando você
disser a pasta, confere o conteúdo com a sua senha (`conferir-copia`). As cópias em claro de antes seguem em claro no
disco D:: o que fazer com elas é decisão sua, e a sessão pergunta.

## Se algo der errado

- **O lançador recusa abrir.** Leia a mensagem: ela diz o que mudou e traz o comando pronto. O motivo mais comum é um
  preparo que faltou (passo 2).
- **O canário reprovou ou não mediu.** Nada abre pela jaula sem o canário aprovando o modo; as outras coisas seguem como
  na 1.7.10.2. Volte à sessão da raiz.
- **Voltar para a 1.7.10.2.** Rode o preparo da 1.7.10.2 na mesma ordem (Windows, depois Ubuntu). O `desfazer` da
  atualização devolve o código do kit; o banco não é tocado. A cópia cifrada não volta a ser em claro sozinha; as cópias
  já cifradas só abrem com a sua senha.

## Limites (registre sempre)

- Com a raiz em `/mnt/e`, o isolamento entre projetos continua lógico (DECISAO-007). A jaula é a barreira do que a ficha
  abre, não uma garantia sobre o projeto inteiro.
- Com o modo sem perguntas ligado e o conector do escritório gravando, uma página ou um documento malicioso pode tentar
  levar a sessão a gravar dados do escritório sem que você veja antes. Ligue só quando quiser.
- Não foi medido ainda: o canário novo, o sandbox próprio do Codex dentro da jaula e os domínios que ele usa, o
  sandbox do Chromium e o plano do ChatGPT. As medidas e o que fica para a 1.7.12 estão em `MUDANCAS-1.7.11.md`.
- Fica para a 1.7.12: a caixa das skills com scripts (S4) e um UAC só para a âncora, a ferramenta e a chave da cópia.
