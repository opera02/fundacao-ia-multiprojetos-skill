# Revisão de segurança — <skill/fundação/projeto> — <versão anterior>..<versão nova>

> Relatório de trabalho PRIVADO, somente leitura: a revisão não altera nada na árvore revisada e o relatório fica
> fora dela (ex.: `entrega/auditoria/` da árvore de desenvolvimento, gravado com hash). Redija: sem credenciais,
> dados pessoais, caminhos internos de clientes nem trechos de caso. Traduzido e adaptado do modelo de revisão de
> segurança do vibe-coding-toolkit (MIT; análise de 21/10/2026; aviso de copyright e licença em
> `<skill>/AVISOS-DE-TERCEIROS.md`). Apague os campos opcionais que não usar; preserve o quadro de afirmações.

## Regras de escrita — leia antes de começar e confira antes de entregar

Valem para o relatório inteiro e para a resposta final; não precisam ser copiadas para o relatório [Decisão;
calibração da 1.7.9 em 25/10/2026: as falhas de precisão dos dois modelos vieram destas seis situações]. Para
auditar só lendo a fundação em uso, use o esqueleto enxuto `assets/templates/AUDITORIA-SEGURANCA.md`, com
estas mesmas regras; este modelo completo é o da revisão de uma versão.

1. **Frase de fato cita a evidência:** o comando exato, copiado da chamada que você fez, e o trecho literal da
   saída, redigido (credencial, dado pessoal ou trecho de caso viram `[redigido]`). Sem trecho, retire a frase ou
   leve-a às pendências como não verificada. Número só copiado de uma saída que conta (`wc -l`, `grep -c` ou o
   total que o comando imprime), nunca contado a olho. Hash copiado inteiro; abreviado ("começo…" ou
   "começo…fim"), só com o hash inteiro em outro ponto do relatório.
2. **Saída cortada sustenta só o que mostra.** `head`, `tail`, limite de resultados ou paginação cobrem as linhas
   exibidas. Corte é o que a saída mostra, não o que o comando permitia: `head -50` que exibiu 12 linhas não cortou
   nada; imprima a contagem (`wc -l`) para saber; se o próprio comando tem limite e o total chega a ele, conte como
   cortada. Para falar de um conjunto ("os arquivos de X", "todos", "nenhum",
   "só", "em nenhum ponto"), rode a busca sem corte sobre esse conjunto, dentro do escopo autorizado; se o conjunto
   passar do escopo, não amplie o escopo para obter a prova: nomeie só o que viu ("nos N arquivos listados") ou
   deixe "não medido".
3. **O que um comando percorre é o que ele percorre.** Filtrar a saída (`grep -v`, `head`) não delimita a leitura.
   Para não tocar `projects/` nem `state/`, delimite na própria busca, com o início absoluto e as duas pastas
   (`find <raiz> -type d \( -name projects -o -name state \) -prune -o -type f -print`,
   `grep -r --exclude-dir=projects --exclude-dir=state`; no PowerShell, `-Exclude` não poda:
   `Get-ChildItem -Force -LiteralPath <raiz> | Where-Object Name -notin 'projects','state' | Get-ChildItem -Force -Recurse -File`;
   `-path` com início absoluto, barra invertida ou barra no fim não poda nada), e copie esse comando no registro de
   operações. Descreva o método copiando os
   comandos, nunca de memória, e não afirme que um comando excluiu, delimitou ou cobriu algo: o comando diz. Antes
   de entregar, confira a lista inteira: travessia de `projects/` ou `state/` sem poda, saída cortada usada como
   evidência ou leitura fora do previsto vão para as divergências de método, declaradas.
4. **Sem autorização expressa do pedido para executar** (a revisão de liberação, por exemplo, roda a suíte numa
   cópia descartável da árvore de desenvolvimento), não copie a árvore revisada nem execute o código ou a suíte
   dela, nem numa cópia: copiar percorre pastas protegidas, e executar é efeito que o pedido não cobre. Testes não
   executados vão para as pendências.
5. **Campo de apoio não traz fato novo.** Origem, contraevidência, correção, contexto e quem consegue disparar
   precisam da mesma evidência que o achado; sem ela, escreva "não medido". Alcance entre contas, pastas acima da
   raiz ou execução real dependem de pré-requisitos: sem conferi-los, o impacto fica condicional.
6. **A resposta final não acrescenta nada:** o caminho do relatório, os títulos dos achados com severidade e
   confiança, e os limites ou onde estão no relatório. Sem resumo do que "está bem" nem conclusão mais forte que a
   do relatório. Se o pedido mandar salvar a resposta num arquivo, salve o mesmo texto da resposta: uma versão só.

## Escopo

- Revisor, cliente e data (outro contexto); autoria/provedor da fonte apenas se documentados, senão não medidos:
- Modo: repositório inteiro | diff exato (base e head por commit; comparação ponta a ponta ou desde a base comum)
- Diferença revisada (base..head, por commit): `<base>..<head>` — na liberação da skill, a base é o commit testado da
  versão anterior (ou um anterior a ele) e, depois do head, só podem mudar arquivos que não são código
- Camadas incluídas: commits, mudanças não commitadas, arquivos não rastreados (cada uma à parte):
- Autorização aplicável e exclusões previstas (como dados de projetos e state/):
- Acessos efetivos e divergências do escopo previsto, conferidos nas ferramentas: listar nomes acessa metadados;
  calcular hash lê conteúdo. Essas operações também exigem autorização e não cabem em "não lido".
- Ativos, entradas, identidades e papéis, projetos e casos, fronteiras de confiança:
- Suposições sobre o ambiente que precisam de confirmação:

## Cobertura e evidência

- Caminhos revisados e excluídos (com o motivo):
- Ferramentas e referências usadas, com versão:
- Comandos e testes rodados, com o isolamento e o resultado (estático · simulado · execução real):
  registre as operações efetivas na tabela abaixo; tarefas não executadas ficam nas pendências. Use caminhos
  absolutos e não mude o diretório do shell para dentro da árvore revisada: o Claude Code com sandbox cria
  `.claude/.cc-writes` no diretório atual do shell.

- Invariância dos arquivos cobertos: SHA-256 antes = depois (manifesto); diretórios, metadados e efeitos
  fora dessa cobertura exigem evidência própria ou ficam não medidos:

### Registro das operações usadas como evidência

Preencha a partir das chamadas e dos resultados disponíveis, antes do quadro de afirmações.
Inclua as operações citadas para sustentar método, leituras, ausências, erros e recusas.
Quando houver recibos externos, identifique a operação pelo ID e confira comando e resultado.
Distinga o recibo recebido na saída de uma consulta da cópia salva depois: o controlador pode acrescentar a
própria consulta entre esses momentos. Conte e calcule o hash da cópia efetivamente entregue; não atribua a ela
a quantidade lembrada da saída anterior. Preserve a cópia e informe seus valores nos campos abaixo, somente
quando esse recibo estiver disponível:

- Recibo SHA-256: <hash dos bytes da cópia entregue>
- Operações no recibo: <quantidade na cópia entregue>

Não reconstrua uma chamada ou uma saída a partir de lembrança ou plano. Se faltar a fonte,
registre somente que a operação não foi comprovada; isso não prova execução sem captura,
erro retornado nem defeito do controlador. Uma ressalva de falta de recibo não autoriza
relatar como ocorrido o comando ou resultado que ele não comprova.

| Operação efetivamente emitida e alvo | Fonte da execução: chamada ou comando e trecho observado | Resultado retornado | Linhas na saída e exibidas | Conclusão permitida |
| --- | --- | --- | --- | --- |
| <operação e alvo reais> | <fonte recuperável no rastro: o comando copiado> | <resultado literal ou resumo fiel> | <total contado (wc -l) e exibidas; cortada se o total passa das exibidas ou se o comando tem limite próprio e o total chega a ele> | <conclusão limitada a esse resultado> |

Uma listagem sem um arquivo sustenta sua ausência naquela listagem, não uma tentativa de abri-lo ou um
erro de leitura. Um impedimento previsto pelo escopo sustenta "não executado por limite de escopo";
"o código mostrou" exige leitura efetiva do código. Não execute algo desnecessário só para preencher a
tabela. Sem fonte da operação, retire a alegação de que ela ocorreu e preserve apenas o fato sustentado.

## Quadro de afirmações — preencha antes de redigir os achados

Este quadro é obrigatório no relatório. Use uma linha por afirmação relevante de presença, ausência, alcance,
causa ou autoria, inclusive as que irão ao título, às pendências e à resposta final. Separe o fato observado da
conclusão que depende de outras condições. Não preencha lacunas para completar o relatório.

| ID | Afirmação que a evidência permite publicar | Fonte e trecho/resultado exato | Escopo efetivamente examinado | Estado: observado, condicional ou não medido | Condições ainda não verificadas |
| --- | --- | --- | --- | --- | --- |
| A1 | <frase limitada ao que foi conferido> | <arquivo:linha, comando/resultado ou registro> | <arquivos, identidades e janela cobertos> | <estado> | <condições ou nenhuma> |

Regras para preencher e conferir:

- Ausência só vale no conjunto examinado: escreva "não localizado nas fontes X e Y". Fontes excluídas ou
  inacessíveis ficam não medidas; não conclua que o registro ou a proteção não existem.
- Metadados permitem descrever o estado observado. Acesso efetivo e impacto entre identidades exigem verificar
  também os pré-requisitos do caminho; sem isso, a conclusão inteira permanece condicional.
- Ocorrência após uma ação não prova sua causa. Registre a sequência observada; atribua o mecanismo somente com
  reprodução ou evidência que o vincule. Autoria e provedor também precisam de fonte, não de suposição.
- Confira acessos nas operações completas e nos resultados. Uma saída truncada não prova que a operação deixou
  de percorrer outros caminhos. Diferencie nome, metadado, leitura de conteúdo e escrita.
- Para afirmar o que um script consulta, identifique o trecho lido que realiza essa consulta. O nome de uma
  ferramenta de inventário ou auditoria não comprova consulta de âncoras, ACLs ou isolamento. Sem trecho ou
  resultado específico, retire essa atribuição; não a complete pelo nome ou por função presumida.
- Uma frase sem suporte suficiente é removida ou reescrita como condicional/não medida. Uma ressalva em outra
  linha não corrige a frase. Não amplie o escopo para obter a prova: registre a limitação.

Redija os achados a partir deste quadro. Cite os IDs usados; o título e cada conclusão herdam as condições das
linhas citadas. Se a observação é confirmada e a exploração é hipotética, dê título à observação e mantenha a
exploração no cenário condicional.

## Achados

Repita por achado comprovado ou hipótese rotulada. Achado sem cenário de falha concreto é palpite: vai para
"Pendências". Se não houver achados, declare em linha própria: `Nenhum achado comprovado no escopo.`

### <ID> — <título>

- Severidade (crítica · alta · média · baixa) e por quê:
- Confiança: <alta | média | baixa>
- Situação da observação: confirmada | a validar
- Alcance e impacto: demonstrados | condicionais; pré-requisitos conferidos e os que faltam:
- Origem: introduzido nesta versão | regressão | preexistente | indeterminado
- Local: arquivo:linha e revisão (ou camada não commitada)
- Evidência: IDs do quadro de afirmações, comando e trecho literal redigido, e caminho da entrada à operação sensível (observado ou condicional):
- Quem consegue disparar e com que pré-requisitos (identidade, permissão, arquivo):
- Cenário de falha concreto (a entrada ou o estado que faz quebrar) e impacto:
- Contraevidência considerada; reprodução ou teste, ou a prova que falta:
- Correção estreita proposta e próxima validação:

Declare confiança individualmente em cada achado, separada da severidade. Confiança geral no método ou uma
ressalva sobre exploração não preenche esse campo. Não invente achado nem confiança para completar o modelo.

## Conferência formal antes da entrega

- Relatório redigido e guardado em local privado, conferido:

Confira o preenchimento com `scripts/verificar_revisao_seguranca.py`, recurso da skill, sem executar o código
auditado. Ele recebe somente JSON por stdin: `relatorio` contém o Markdown e `recibo_texto`, quando houver,
contém o literal da cópia entregue. Não abre os caminhos escritos nesses dados, não grava nem consulta rede.
Use somente arquivos próprios e autorizados. Com recibo externo, o comando abaixo preserva bytes UTF-8 e CRLF:

```sh
python -I -B -X utf8 -c "import json,sys; from pathlib import Path; print(json.dumps({'relatorio':Path(sys.argv[1]).read_bytes().decode('utf-8'),'recibo_texto':Path(sys.argv[2]).read_bytes().decode('utf-8')},ensure_ascii=False))" "<relatorio>" "<copia-do-recibo>" | python -I -B -X utf8 "<skill>/scripts/verificar_revisao_seguranca.py"
```

No Ubuntu, use `python3` se esse for o comando do ambiente. Sem recibo externo, envie somente `relatorio` no
JSON, sem inventar recibos. O conferidor exige em cada achado local (com linha, registro ou "metadado"),
evidência, cenário, impacto e uma confiança, cada um na mesma linha do campo. Nos achados, na coluna de afirmação
do quadro, no título e no texto antes da primeira seção (fora de citação) e em seção fora deste modelo, aponta
afirmação de alcance ("nenhum", "só", "todos",
"qualquer", "não há", "é seguro") sem cobertura declarada ("não localizado nas fontes X", "busca sem corte",
"condicional", "não medido"), recusa seção de avaliação positiva e recusa hash abreviado ("começo…fim") sem o hash
inteiro correspondente em outro ponto do relatório. Escopo e cobertura não passam pela regra de alcance — lá
"só" e "nenhum" descrevem o próprio método —, mas continuam sujeitos às regras de escrita. Nas pendências, "só",
"somente", "apenas" e "único" são recusados: pendência diz o que não foi verificado, não o que foi.
Corrija o próprio rascunho a partir dos erros e dos valores observados na cópia e repita a conferência antes de
entregar. Se não puder executá-la dentro do escopo, deixe essa prova pendente.
O interpretador lê o próprio script e suas dependências; a ausência de abertura de arquivos refere-se aos
caminhos de dados recebidos pelo conferidor, não ao processo inteiro.

Código zero e `preenchimento_ok` conferem somente campos e coerência dos literais fornecidos. O conferidor não
autentica o recibo nem verifica mérito, suporte das afirmações, comandos, acesso ou qualidade. Ainda é necessário
comparar afirmações com fontes/rastro e obter a revisão independente aplicável; não declare a auditoria aprovada
apenas porque essa conferência passou.

Antes de fechar, confira cada afirmação de ação realizada contra o registro de operações e seu resultado.
Depois releia título, achados, pendências e resposta final contra o quadro e o rastro. Corrija ou
remova qualquer afirmação que exceda sua linha de evidência. A resposta final informa onde está o relatório e
reproduz somente conclusões já conferidas, com as mesmas condições; não acrescenta uma conclusão mais forte.

## Pendências e limites

- Hipóteses não comprovadas e a evidência que falta:
- Endurecimento sugerido (separado dos achados):
- Lacunas de cobertura e próxima validação útil:

Esta revisão não estabelece que a versão é segura nem certifica conformidade. Achados e confiança valem para o
escopo e as evidências registrados, não além deles. Nenhuma correção foi aplicada pela revisão.
