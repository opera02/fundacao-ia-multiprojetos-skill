# Auditoria de segurança somente leitura — <fundação ou projeto> — <data>

> Relatório PRIVADO, gravado fora da árvore auditada. Esqueleto enxuto para auditar a fundação em uso só lendo; a
> revisão de segurança de uma versão (diff) usa `assets/templates/REVISAO-SEGURANCA.md`. Valem as seis regras de
> escrita do topo daquele modelo. Este esqueleto tem só os campos de que a auditoria precisa: não acrescente
> resumo, contexto nem avaliação. Cada frase de fato cita o número do comando (C1, C2, ...) que a sustenta.
> Adaptado do modelo de revisão de segurança do vibe-coding-toolkit (MIT; aviso em `<skill>/AVISOS-DE-TERCEIROS.md`)
> [Decisão; calibração da 1.7.9 em 25/10/2026: as afirmações sem base estavam nos resumos do método, na resposta,
> em números, cortes, hashes e números de comando que não conferiam com a saída, em fatos novos fora do quadro e em
> pendências que descreviam o que foi feito].

## Escopo

- Pedido (copiado):
- Fora do escopo por regra: dados de `projects/`, `state/` (banco e trilha), web, execução do código auditado e
  sondar o host: o inventário do ambiente (`inspecionar_ambiente.py`) lê PATH, algumas variáveis de ambiente e
  `/proc` e, no Windows, o registro; não rode.
- Invariância: Nº dos comandos do manifesto SHA-256 antes e depois, com poda de `projects/` e `state/` na própria
  busca (calcular hash lê conteúdo), e o resultado copiado (antes = depois); o que fica fora do manifesto e o efeito
  dos comandos emitidos antes do primeiro manifesto: não medidos.
- Divergências de método: as linhas da tabela de comandos com travessia sem poda, saída cortada usada como
  evidência ou leitura fora do previsto, cada uma pelo número.

## Comandos executados

Grave a saída inteira de cada comando num arquivo com o número dele, numa pasta temporária nova, fora da árvore
auditada e do relatório, e imprima a contagem antes das linhas. Crie a pasta uma vez, com nome imprevisível (pasta de
nome fixo pode já existir e ser de outra conta), e use nos comandos seguintes o caminho que a criação imprimiu, escrito
por extenso no lugar de `<aud>` (variável do shell não passa de uma chamada para a outra). Ponha o comando inteiro,
mesmo composto, entre as chaves; em POSIX:

```sh
mktemp -d "${TMPDIR:-/tmp}/aud.XXXXXXXX"
{ <comando>; } > "<aud>/C1.txt" 2>&1; wc -l < "<aud>/C1.txt"; head -80 "<aud>/C1.txt"
```

No PowerShell:

```powershell
$p = Join-Path ([IO.Path]::GetTempPath()) ("aud-" + [guid]::NewGuid().ToString("N")); New-Item -ItemType Directory -Path $p | Out-Null; $p
& { <comando> } *>&1 | Out-File -Encoding utf8 -Width 4096 "<aud>\C1.txt"; (Get-Content "<aud>\C1.txt").Count; Get-Content "<aud>\C1.txt" -TotalCount 80
```

Use caminhos absolutos e não mude o diretório do shell (`cd`, `pushd`, `Set-Location`) para dentro da árvore
auditada: o Claude Code com sandbox cria `.claude/.cc-writes` no diretório atual do shell, e isso altera a árvore.
Comando que precisa de pasta usa a opção dele (`find <pasta>`; no PowerShell, `Get-ChildItem -LiteralPath <pasta>`)
ou, em POSIX, um subshell `( cd <pasta> && <comando> )`, que não muda o diretório do shell. Sessão aberta dentro da
árvore ganha essa pasta na raiz dela sem nenhum `cd`: declare-a na invariância. Não rode `git` na árvore auditada: a
configuração dela (`.git/config` e o que ele inclui) pode rodar programas por qualquer chave que aponte para comando
(por exemplo `core.hooksPath`, `core.fsmonitor`, `core.sshCommand`, `filter.<x>.clean/smudge/process`,
`diff.<x>.command/textconv`, `credential.helper`, `include/includeIf`; também `diff.external` e `gpg.program`); se
precisar, leia antes essa configuração e só rode
`git -c core.fsmonitor=false --no-optional-locks -C <pasta>` sem programa configurado. A poda vale pelo nome das
duas pastas: `find <raiz> -type d \( -name projects -o -name state \) -prune -o -type f -print`,
`grep -r --exclude-dir=projects --exclude-dir=state`; no PowerShell, `-Exclude` não poda: use
`Get-ChildItem -Force -LiteralPath <raiz> | Where-Object Name -notin 'projects','state' | Get-ChildItem -Force -Recurse -File`.

O número do arquivo é o do comando: numere na ordem em que emitiu e não renumere. Comando emitido antes de ler este
esqueleto, ou na mesma resposta que pediu a leitura, também entra na tabela, com o número na ordem em que saiu: sem
arquivo gravado, a coluna de linhas diz "não gravada" e ele não sustenta afirmação (a conferência não tem o que
reler); se percorreu `projects/` ou `state/` sem poda, ou leu fora do previsto, vai para as divergências de método.
Para usar o resultado dele, repita-o gravando (com a poda, se ele não a tinha), com número novo.
Não ponha limite dentro das chaves (`head`, `grep -m`): o limite fica só na exibição. A pasta guarda saídas sem
redação: apague-a depois da conferência, e o relatório não aponta para ela (a evidência é o trecho copiado na tabela).
Leitura feita com a ferramenta Read também entra na tabela, com número; na coluna de linhas vai o intervalo que a
saída numerou, e o arquivo só é "inteiro" com o `wc -l` dele na tabela. Ela não grava arquivo: o trecho vem da
saída da ferramenta, e a conferência relê o mesmo intervalo.

Na tabela, o comando exato é o que está entre as chaves, copiado como foi emitido, na ordem, com o número; escreva
cada `|` como `\|`. Não resuma o que ele fez, cobriu ou deixou de fora: o comando é a descrição do método. A saída
está cortada se o `wc -l` passa das linhas exibidas, ou se o comando entre as chaves tem limite próprio e o
`wc -l` chega a ele. Com recibos externos de operações, siga também o registro de operações do modelo completo
(Recibo SHA-256 e Operações no recibo da cópia entregue).

| Nº | Comando exato | Percorre `projects/` ou `state/`? Com poda na própria busca? | Linhas na saída (`wc -l`) e exibidas | Trecho literal usado como evidência (redigido) |
| --- | --- | --- | --- | --- |
| C1 | <comando como foi emitido> | <não; ou sim, com ou sem poda> | <número copiado do wc -l; exibidas: todas, ou as primeiras 80> | <linhas copiadas do arquivo do comando> |

## Quadro de afirmações

| ID | Afirmação que a evidência permite publicar | Fonte: Nº do comando e trecho | Escopo efetivamente examinado | Estado: observado, condicional ou não medido | Condições ainda não verificadas |
| --- | --- | --- | --- | --- | --- |
| A1 | <frase limitada ao que o comando mostrou> | <C3: trecho> | <arquivos ou caminhos percorridos> | <estado> | <condições ou nenhuma> |

No quadro, só as afirmações que um achado ou a invariância usam: controle conferido sem achado não entra (o
relatório não lista o que está bem). Número, contagem e lista vêm da saída, copiados: do `wc -l` do arquivo do
comando, de `grep -c` sobre ele ou do total que o comando imprime; não conte a olho. Saída agrupada por parte da
linha (`uniq -w`, `-f` ou `-s`; `sort -u -k`) mostra um representante por grupo: o resto da linha dele não vale para
o grupo. O resultado de um filtro não vale para outro atributo (a lista de nomes achados por um padrão não diz o que
os arquivos contêm). Ausência só vale no que o comando percorreu. Hash é copiado inteiro; abreviado ("começo…" ou
"começo…fim"), só com o hash inteiro em outro ponto do relatório.

## Achados

Repita por achado comprovado ou hipótese rotulada. Achado sem cenário de falha concreto é palpite: vai para
"Pendências". Sem achado comprovado, escreva em linha própria: `Nenhum achado comprovado no escopo.`

Nos achados, não entra fato que o quadro não tenha: título, local, situação, cenário, impacto, severidade e
correção usam as afirmações do quadro, pelo ID, sem ampliar o conjunto nem o atributo (o que o quadro diz de um
filtro não vira outro atributo no título); o que o quadro não tem fica condicional ou não medido. Fato de método,
nas divergências e nas pendências, cita o Nº do comando.

### F1 — <título: a observação, não a exploração>

- Situação da observação: confirmada | a validar
- Local: arquivo:linha (para modo de arquivo, o arquivo e "metadado")
- Evidência: Nº do comando, trecho literal redigido e IDs do quadro
- Cenário de falha concreto (condicional se depender de pré-requisito não conferido):
- Impacto (demonstrado | condicional, com os pré-requisitos que faltam):
- Severidade (crítica · alta · média · baixa) e por quê:
- Confiança: <alta | média | baixa>
- Correção estreita proposta:

## Pendências e limites

Diga o que não foi verificado e por quê. O que foi feito está na tabela de comandos, e a pendência não o descreve.

- Hipóteses não comprovadas e a evidência que falta:
- Não verificado, com o motivo:
- Endurecimento sugerido (separado dos achados):

Esta auditoria não estabelece que a fundação é segura. Nenhuma correção foi aplicada.

## Conferência formal antes da entrega

Primeiro, confira o rascunho contra as saídas gravadas, no arquivo do comando citado: cada número com `wc -l` ou
`grep -c`; cada trecho literal com `grep -F -- '<pedaço do trecho>' "<aud>/C1.txt"`, usando um pedaço sem
"…" nem "[redigido]" (no PowerShell, `Select-String -SimpleMatch`); e cada "Cn" do texto, listado com
`grep -n 'C[0-9]' "<relatorio>"`, com o fato que ele sustenta no arquivo Cn.txt (na leitura feita com Read, relendo
o mesmo intervalo). Corrija ou retire o que não conferir.

Depois, confira o preenchimento com o conferidor da skill, sem executar o código auditado; sem recibo externo, o
JSON leva só o relatório:

```sh
python -I -B -X utf8 -c "import json,sys; from pathlib import Path; print(json.dumps({'relatorio':Path(sys.argv[1]).read_bytes().decode('utf-8')},ensure_ascii=False))" "<relatorio>" | python -I -B -X utf8 "<skill>/scripts/verificar_revisao_seguranca.py"
```

Com recibo externo, use o comando do modelo completo, que envia também `recibo_texto`. No Ubuntu, use `python3`
se esse for o comando do ambiente. O conferidor também recusa hash abreviado que não confere com um hash inteiro
do relatório; a lista do que ele confere está na Conferência formal do modelo completo. Corrija o rascunho a partir
dos erros e repita a conferência antes de entregar. `preenchimento_ok`
confere campos e forma, não o mérito: ainda é preciso reler cada frase contra a tabela de comandos e obter a
revisão independente aplicável; não declare a auditoria aprovada apenas porque essa conferência passou.

## Resposta final

Preencha este parágrafo. Se o pedido mandar salvar a resposta num arquivo, grave-o lá e responda com o texto do
arquivo, copiado da saída de `cat`; sem arquivo, responda com o parágrafo. A resposta é esse texto, sem acréscimo
nem corte: divergência, invariância e pasta criada por engano ficam no relatório.

Relatório: <caminho>. Achados: <ID — título, severidade, confiança, copiados dos achados>
(ou "nenhum achado comprovado no escopo"). Limites, pendências e divergências de método: no relatório.
Esta auditoria não estabelece que a fundação é segura.
