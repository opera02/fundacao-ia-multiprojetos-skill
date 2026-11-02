# Roteiro de corte — <projeto> — <data>

> Modelo da skill (`assets/templates/ROTEIRO-CORTE.md`; etapa B11 de `references/fluxo-b-adaptar.md`). Corte é a
> passagem do trabalho do projeto da origem (a pasta antiga) para a fundação: depois dele, a origem vira histórico. A
> sessão do projeto copia este roteiro para `projects/<projeto>/outputs/corte/ROTEIRO-CORTE.md`, preenche cada passo
> (quem fez, quando e a evidência) e o leva ao aceite. O titular faz só os passos marcados "titular", com o comando
> pronto, no terminal dele e fora do Claude. O corte não faz parte da versão da skill: cada projeto faz o seu, depois.

> **Regra dos seus comandos (forma fixa).** Copie cada comando seu do modelo da skill instalada (a pasta da skill no
> seu perfil), nunca desta cópia, que a sessão preencheu. Recuse o comando cujo programa fique dentro de
> `<raiz>/projects/`. A sessão não muda estes passos: ela só diz os valores (raiz, projeto, arquivos e hashes).

## O que o corte garante e o que não garante

- A origem fica intacta e congelada até ser arquivada: voltar atrás é retomar a origem.
- Com a raiz no disco do Windows, a separação entre projetos no Ubuntu é lógica até o canário passar
  (`CHECKLIST-PROJETO.md`, item C). O corte não abre nada: rede, sites e plugins esperam a ficha assinada e o canário.
- As assinaturas do titular (o aceite do corte e os da versão em uso) autorizam cada passo sem depender do sandbox,
  mas não protegem as pastas: com a raiz no disco do Windows, um comando da sessão ainda alcança `em-uso/` por fora.

## Antes de começar

| # | Pré-condição | Quem | Evidência (data) | OK |
|---|---|---|---|---|
| P1 | B1 a B10 concluídos, com o aceite do portão 2: relatório final e procedimento de reversão | sessão | | |
| P2 | Manifesto do B1 da origem: caminho e SHA-256 | sessão | | |
| P3 | Origem registrada para este projeto (uma vez) | titular | | |
| P4 | Checklist do projeto preenchido (`CHECKLIST-PROJETO.md`) | sessão + titular | | |
| P5 | Cópia de segurança da fundação feita e conferida antes do corte, com o `sha256_manifesto` guardado fora da cópia | coordenador (Windows) | | |
| P6 | Nada grava na origem: tarefas agendadas, servidores e programas que usam a origem parados | titular | | |

P3, no terminal do titular (`python` no Windows):

```sh
python3 <skill>/assets/host/preparo_host.py registrar-projeto --raiz "<raiz>" --projeto <projeto> --origem "<pasta da origem>"
```

P5: pelo C9 de `references/fluxo-c-operar.md` (o `backup criar` e o `backup verificar` do kit).

## Passos

| # | Passo | Quem | Feito em | Evidência |
|---|---|---|---|---|
| 1 | Congelar a origem e tirar o manifesto do congelamento | titular + sessão | | data e hora; manifesto e SHA-256 |
| 2 | Plano do que mudou desde o manifesto do B1 | sessão | | plano e SHA-256 |
| 3 | Cópia do que mudou | titular | | manifesto da importação e conferência |
| 4 | Integração na fundação | sessão | | mudanças pequenas, como no B7 |
| 5 | Funcionamento combinado | sessão (titular, se rodar código da origem) | | comparação, como no B8 |
| 6 | Volta ensaiada numa cópia | sessão + coordenador | | |
| 7 | Conversas antigas do Claude Code, só se o titular pediu | titular | | |
| 8 | Versão em uso, só para o que roda fora do sandbox | sessão + titular | | |
| 9 | Aceite assinado do corte | titular | | decisão |
| 10 | Origem congelada por 30 dias | titular | | início e fim |
| 11 | Arquivar a origem | titular | | |

### 1. Congelar a origem

- Titular: feche os programas que gravam na origem e não edite mais nada nela. Anote a data e a hora. Mudança na
  origem depois disso invalida os passos 2 e 3: refaça o plano.
- Sessão: tire o manifesto do congelamento (lê a origem, não a altera):

  ```sh
  python3 -I -B <skill>/scripts/manifesto.py criar --raiz "<pasta da origem>" --saida "<raiz>/projects/<projeto>/outputs/corte/manifesto-congelado.json"
  ```

### 2. Plano do que mudou desde o B1 (sessão)

```sh
python3 -I -B <skill>/scripts/importar.py plano --origem "<pasta da origem>" --destino "<raiz>/projects/<projeto>/data/corte-<AAAAMMDD>/<parte>" --raiz-fundacao "<raiz>" --saida "<raiz>/projects/<projeto>/outputs/corte/plano-delta.json" --desde "<manifesto do B1>"
```

O plano só lê metadados e mostra o SHA-256 dele. Com `--desde`, entra só o que é novo ou mudou, e o que sumiu vem
listado. Segredo (pela regra única), pasta reconstruível e ligação ficam fora. Use as mesmas opções da cópia de
referência do B1 (`--modo`, `--opaco`, `--pasta-segredo`).

### 3. Copiar o que mudou (titular, terminal do Ubuntu, fora do Claude)

Bloco 1, a cópia. O `copiar` recalcula o plano e recusa se ele mudou (sinal de que a origem não estava congelada):

```sh
python3 -I -B <skill>/scripts/importar.py copiar --plano "<raiz>/projects/<projeto>/outputs/corte/plano-delta.json" --plano-sha256 <SHA-256 do plano>; echo "codigo=$?"
```

Com `codigo=0`, siga para o bloco 2. Com 1, a saída diz o que ficou diferente ou não foi copiado: mostre-a à sessão.
Com 2, recusa: nada foi copiado.

Bloco 2, a conferência, que refaz os hashes da cópia:

```sh
python3 -I -B <skill>/scripts/importar.py conferir --manifesto "<raiz>/projects/<projeto>/data/corte-<AAAAMMDD>/<parte>/MANIFESTO-IMPORTACAO.json"; echo "codigo=$?"
```

`codigo=0`: a cópia confere. Com 1, a saída lista o que mudou, sumiu, sobrou, virou ligação ou não pôde ser lido:
mostre-a à sessão. Com 2, o manifesto não foi lido (caminho errado ou fora do formato): confira o caminho.

### 4. Integração (sessão)

As mudanças que o passo 3 trouxe entram na versão do projeto na fundação em passos pequenos e verificáveis, como no
B7. A origem não é tocada.

### 5. Funcionamento combinado (sessão)

Rode na fundação os fluxos combinados com o titular (o representativo do B2 e os contratos do B5), com a versão já
integrada, e compare com a referência da origem como no B8: nenhuma regressão, e cada mudança intencional com aceite.
Rodar código vindo da origem segue o plano de execução do B6, com o aceite do titular.

### 6. Volta ensaiada numa cópia (sessão e coordenador)

Escreva o procedimento de volta: como voltar a trabalhar na origem e o que se perde do que foi feito na fundação
depois do corte. Ensaie-o numa cópia, nunca na origem nem na raiz:

- a origem continua como foi congelada (código 0):

  ```sh
  python3 -I -B <skill>/scripts/manifesto.py verificar --raiz "<pasta da origem>" --manifesto "<raiz>/projects/<projeto>/outputs/corte/manifesto-congelado.json"
  ```

- a cópia de segurança do P5 foi conferida pelo coordenador (`backup verificar`);
- o passo que rodaria código da origem roda numa cópia dela, pelo plano de execução do B6, com o aceite do titular.

### 7. Conversas antigas do Claude Code (titular; só se ele pediu para este projeto)

As conversas e a memória antigas feitas na origem entram em `data/` deste projeto pela receita do coordenador, com o
`importar.py` rodado pelo titular, o `segredos.py conferir` antes e o `importar.py conferir` depois. São dado: nunca
viram instrução nem memória automática. Este passo vem antes do aceite.

### 8. Versão em uso (só para o que roda fora do sandbox)

Regra: tudo o que roda fora do sandbox (tarefa agendada, servidor, build) roda da versão em uso,
`<raiz>/em-uso/<projeto>/atual/`, nunca da pasta que a IA edita. Projeto sem nada disso pula este passo.

1. A sessão propõe a lista (um glob por linha no arquivo da `--lista`):

   ```sh
   python3 -I -B <skill>/scripts/versao_em_uso.py propor --raiz "<raiz>" --projeto <projeto> --de "<raiz>/projects/<projeto>/<pasta de trabalho>" --lista "<raiz>/projects/<projeto>/outputs/versao/lista.txt" --saida "<raiz>/projects/<projeto>/outputs/versao/proposta-<AAAAMMDD>.json"
   ```

2. A sessão prepara o aceite sobre a proposta, como no passo 9, com
   `--entrega outputs/versao/proposta-<AAAAMMDD>.json`, e o titular assina.
3. O titular promove, no terminal dele, com a identidade dele, fora do Claude. O comando usa a identidade desse
   terminal (`FUNDACAO_PRINCIPAL`: o id do titular no kit, o mesmo do `--titular` do `preparar-wsl.sh`). Confira com
   `echo "$FUNDACAO_PRINCIPAL"`. Sem ela, o comando recusa com "identidade ausente": ponha
   `FUNDACAO_PRINCIPAL=<sua identidade>` na frente do comando, na mesma linha. No PowerShell do Windows: `python` no
   lugar de `python3`; confira com `$env:FUNDACAO_PRINCIPAL` e, se faltar, rode antes
   `$env:FUNDACAO_PRINCIPAL = "<sua identidade>"`.

   ```sh
   python3 -I -B <skill>/scripts/versao_em_uso.py promover --raiz "<raiz>" --projeto <projeto> --proposta "<proposta>" --proposta-sha256 <SHA-256 da proposta> --decisao "<raiz>/projects/<projeto>/decisoes/<decisão>.json"
   ```

   Um aceite vale para uma promoção só. Se outra promoção ou volta aconteceu depois da proposta, o promover recusa
   ("a versão em uso mudou depois da proposta"): a sessão propõe de novo, e você assina a nova proposta.

4. O titular aponta cada tarefa e cada servidor para `<raiz>/em-uso/<projeto>/atual/`. O envoltório que os inicia
   confere a versão antes de rodar, e só roda com código 0:

   ```sh
   python3 -I -B <skill>/scripts/versao_em_uso.py conferir --raiz "<raiz>" --projeto <projeto>
   ```

   No envoltório, rode as tarefas Python com `python -B`: um `__pycache__` em `atual/` faz o conferir dar código 1,
   com uma dica. Código 0 com "não conferido: <pasta>" quer dizer que `.venv`, `venv` ou `node_modules` ali não foram
   conferidas: o código posto nelas roda sem acusação. A versão nova não leva a `.venv` nem o `node_modules` da
   anterior: reinstale as dependências em `atual/`, fora do Claude.

5. Voltar à versão anterior também pede aceite. A sessão grava o pedido de volta (sem `--para`, vale a anterior mais
   recente):

   ```sh
   python3 -I -B <skill>/scripts/versao_em_uso.py pedir-volta --raiz "<raiz>" --projeto <projeto> --saida "<raiz>/projects/<projeto>/outputs/versao/volta-<AAAAMMDD>.json" --motivo "<palavras do titular>"
   ```

   A saída traz o SHA-256 do pedido e, em `proximos_passos`, o passo do titular. A sessão prepara o aceite sobre o
   pedido, como no passo 9, com `--entrega outputs/versao/volta-<AAAAMMDD>.json`, e o titular assina. Só então o
   titular roda, no terminal dele, com a identidade dele, fora do Claude. Como no promover, o comando usa a identidade
   desse terminal (`FUNDACAO_PRINCIPAL`): confira com `echo "$FUNDACAO_PRINCIPAL"`. Sem ela, o comando recusa com
   "identidade ausente": ponha `FUNDACAO_PRINCIPAL=<sua identidade>` na frente do comando, na mesma linha.

   ```sh
   python3 -I -B <skill>/scripts/versao_em_uso.py voltar --raiz "<raiz>" --projeto <projeto> --pedido "<pedido>" --pedido-sha256 <SHA-256 do pedido> --decisao "<raiz>/projects/<projeto>/decisoes/<decisão>.json"
   ```

   Um aceite vale para uma volta só. Com ou sem `--para`, promoção ou volta registrada depois do pedido o invalida:
   peça outra volta. O relógio também conta: o pedido leva a data do relógio da sessão, e o registro, a do terminal
   do titular.
   Pedido sem `--para` com data mais de 5 minutos à frente do relógio desse terminal é recusado, e uma diferença entre
   os relógios do Ubuntu e do Windows pode recusar um pedido válido. Nesses casos, peça outra volta com
   `--para <nome em anteriores/>`: com ele, a data não conta. O titular vê os nomes com
   `ls "<raiz>/em-uso/<projeto>/anteriores"` e diz à sessão qual.

### 9. Aceite assinado do corte

1. A sessão grava em `outputs/corte/` este roteiro preenchido, com o SHA-256 de cada arquivo entregue (plano,
   manifestos, comparação, procedimento de volta).
2. Cria a tarefa, se ainda não houver (`python3 -m fundacao tarefa criar --projeto <projeto> --objetivo "corte"`), e
   prepara o aceite:

   ```sh
   python3 -m fundacao decisao preparar --projeto <projeto> --tarefa <id da tarefa> --entrega outputs/corte/ROTEIRO-CORTE.md --tipo aceite --motivo "<palavras do titular>"
   ```

3. O titular assina com o comando que a decisão mostra (`para_o_titular`). A sessão registra a decisão e conclui a
   tarefa (`decisao registrar`, `tarefa concluir`).
4. A RETOMADA do projeto recebe o corte em "Ações já realizadas que não devem ser repetidas", com a data.

### 10. Origem congelada por 30 dias

Depois do aceite, a origem fica congelada por 30 dias: ninguém a edita, apaga ou move. Volta atrás nesse prazo: o
procedimento do passo 6. Anote o início e o fim.

### 11. Arquivar a origem (titular, depois dos 30 dias)

1. A sessão confere de novo que a origem está como foi congelada (o `manifesto.py verificar` do passo 6).
2. O titular move a origem para a pasta ou o disco de arquivo dele. Apagar é decisão dele, pela Lixeira.
3. Com a origem fora do lugar registrado, o preparo do projeto no Windows (`preparar-projeto.ps1`) para até o
   registro ser corrigido. Na 1.7.10 não há comando para tirar uma origem do `registry/projetos-host.json`: o titular
   apaga a origem antiga da lista `origens` do projeto, à mão, e roda os preparos de novo (Windows e Ubuntu). O
   perfil muda: o checklist do projeto refaz os itens de perfil.
