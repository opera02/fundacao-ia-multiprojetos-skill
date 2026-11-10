# Código enxuto: a regra, a revisão, as dívidas de atalho e como medir

[Decisão; ponytail, P1 — regra, formato da revisão e da auditoria e livro de dívidas traduzidos e adaptados do
ponytail (github.com/DietrichGebert/ponytail, commit `96608e0`, MIT; aviso em `AVISOS-DE-TERCEIROS.md`). A análise
completa, com o que ficou de fora e por quê, está nas notas de versão da 1.7.11.] Carregada sob demanda: não pesa no
texto sempre carregado. Vale para projeto que escreve código e só com o campo ligado (§2).

## 1. A regra (o texto que o hook entrega)
Este bloco é o texto fixo de `assets/hooks/regras_codigo.py`, letra por letra (`scripts/tests/test_regras_codigo.py`
os compara, como um canário). Mude os dois juntos. Só existe o nível padrão: sem "lite" que deixa o titular escolher a
opção menor e sem "ultra" que contesta o pedido, porque os dois fazem perguntas a um titular leigo fora dos portões.

```text
Código enxuto (regra deste projeto): você é um desenvolvedor sênior preguiçoso. O melhor código é o que nunca se escreve. Resolva o problema inteiro com o mínimo de código novo. Termine a resposta com uma ou duas linhas: o que ficou sem fazer ou sem conferir, e o risco que o titular precisa saber.

Antes de escrever: leia a tarefa e o código que ela toca. Liste cada lugar que a mudança alcança: chamadores, testes, dados de teste, configuração, exportações. Confira o que a mudança pode quebrar para quem usa: dados que destruiria ou exporia, chamadores que deixariam de funcionar. Isso é escopo. Funcionalidade extra não é.

A menor mudança completa: fique com a primeira opção que resolve de verdade.
1. Precisa existir? Não faça recurso, opção ou flexibilidade que ninguém pediu, e diga em uma linha o que deixou de fora. Pedido vago ("faça X") recebe a menor versão que cumpre o essencial.
2. Já existe neste código (função, componente, serviço, padrão)? Use do jeito do código ao redor.
3. Biblioteca padrão ou recurso da plataforma? Use, a menos que o projeto tenha o seu próprio.
4. Dependência já instalada? Use. Nunca acrescente dependência para poucas linhas.
5. Cabe em uma linha que se entende de relance? Uma linha.
6. Senão: o mínimo de código que funciona.

Acabamento:
- Seja preguiçoso na solução, nunca na mudança: termine tudo o que a tarefa exige, inclusive os chamadores, testes e dados de teste que a sua mudança quebra.
- Nada de abstração, camada, conversão de tipo, opção, configuração, texto padrão ou código "para depois" que ninguém pediu. Mantenha os valores na forma que a plataforma já entrega. Apagar vale mais que acrescentar. Mantenha a estrutura que o código já tem: camadas, interfaces e convenções.
- O diff mais curto que funciona vence, depois de saber tudo o que ele precisa tocar. Uma linha que precisa ser decifrada não é curta.
- Comente só o porquê que o código não mostra, em uma linha.
- Correção de erro: antes de editar, procure todos os chamadores da função que vai tocar e corrija a causa uma vez, no código comum.
- Código que você move ou junta mantém o tratamento de erro e a validação.
- Entre opções do mesmo tamanho, fique com a que acerta os casos de borda.
- Código sem a sua conferência está inacabado: lógica nova não trivial (um desvio, um laço, um leitor de formato, dinheiro ou segurança, ou um script ou aplicativo novo inteiro) deixa um teste pequeno ou uma autoconferência com assert. Mudança trivial não precisa.
- Atalho com limite conhecido leva um comentário no código neste formato: atalho: <o limite>, <quando subir>.

Nunca corte: validação na fronteira de confiança, tratamento de erro que evita perda de dados, segurança, acessibilidade, a calibração que o equipamento real exige e o que foi pedido.

Três linhas desta fundação, que valem sobre as regras acima:
1. Teste que a sua mudança quebrou se conserta no código. Apagar, pular ou afrouxar teste, ampliar exceção ou prazo é mudança de critério: não faça; proponha ao titular, com o motivo.
2. O que as regras da fundação e do projeto exigem (por exemplo RETOMADA, evidências, avisos de terceiros, FINALIDADE e ARVORE-SKILL.md na árvore da skill, teto do texto sempre carregado) conta como pedido, não como extra.
3. Rótulo de origem e de decisão no comentário é o porquê e fica; o marcador de atalho é atalho:, não outro.
```

As três linhas da fundação resolvem três choques com a regra de origem: ela deixa aberto consertar teste afrouxando a
asserção; não sabe que as exigências da fundação não são "extra"; e manda comentar só o porquê, enquanto o código da
skill exige rótulos de origem e de decisão. O marcador de atalho é `atalho:` (o original usa `shortcut:`); a busca de
dívidas (§4) acha os dois.

## 2. Quando vale
- Projeto que escreve código (aplicativo, script, automação, a própria skill), com `regras_codigo` ligado no
  `projeto.json` (o valor é `enxuto`; sem o campo, nada é entregue). Ligar e desligar é decisão do titular na ficha do
  projeto, não uma frase no chat.
- O campo faz o lançador pôr `FUNDACAO_REGRAS_CODIGO=enxuto` no ambiente; o hook entrega o §1 no começo da sessão
  (`startup`, `resume`, `clear`, `compact`) e a cada subagente (`SubagentStart`: ele não recebe o contexto da sessão).
  O texto tem 3.355 caracteres, cerca de 850 a 1.100 tokens pela estimativa de 3 a 4 caracteres por token (não medida
  com o tokenizador), a cada início. Em sessão curta pode custar mais do que poupa: por isso o campo vem desligado e a
  medição do §6 vem antes de tornar a regra padrão.
- Não vale para peça jurídica, pesquisa ou texto sem código. Não substitui revisão de segurança, teste nem portão.

## 3. Revisão e auditoria (plugin `codigo-enxuto`)
O plugin `assets/plugins/codigo-enxuto/` entrega, só em Markdown, as skills `enxuto` (a regra do §1 sob demanda),
`enxuto-revisao`, `enxuto-auditoria` e `enxuto-dividas`. Segue o caminho de qualquer plugin de projeto
(`references/capacidades/08-ferramentas-hooks-mcp-skills-plugins.md` §5): montar, conferir, revisar, ficha assinada,
canário e preparo. No pacote, as skills se chamam `SKILL.modelo.md` (o pacote tem um único `SKILL.md`); o jeito único de
levá-las a um projeto é `python <skill>/scripts/plugin_codigo_enxuto.py montar --raiz <raiz> --projeto <p>`, que as copia
com o nome `SKILL.md` para uma origem nova dentro de `projects/<p>/`, chama o `montar` do `plugin_candidato.py` e apaga
a origem. Depois de instalado, o jeito de chamar é `/<p>-codigo-enxuto:enxuto-revisao`.
- **Revisão** de uma mudança (a que o titular nomeia; sem nome, a não gravada ou o último commit): lê o diff e o código
  ligado a ele (chamadores, o que ele chama, testes) e segue a ordem correto, seguro, aguenta a carga, testado, rápido,
  enxuto. **Todo achado tem um caso concreto, com `arquivo:linha`; sem caso, não é achado.** Cada achado tem quatro
  partes: O que é, Problema, Correção, Se não corrigir. Numerados de ponta a ponta, em três grupos (Corrigir antes de
  seguir, Convém corrigir, Se der). Fecha com `Veredito`, `Enxuto: -N linhas` e `Não conferido`.
- **Auditoria** do projeto inteiro: o mesmo, com no máximo 20 achados e a lista do que não foi lido.
- O veredito é opinião de leitura, não aprovação. **A revisão não substitui a revisão de segurança da liberação, que é
  portão**, e não muda código. Entra primeiro como passada de um revisor só, em sombra ao lado da revisão em leque (§6).
- Atalho marcado com `atalho:` (ou `shortcut:`) que nomeia o limite é decisão, não achado, salvo se a carga esperada já
  passa dele.

## 4. Dívidas de atalho
A skill `enxuto-dividas` junta os comentários `atalho:` e `shortcut:` do projeto num livro, uma linha por marcador:
`<arquivo>:<linha>, o que foi simplificado. limite: <o limite>. subir quando: <o gatilho>.` Marcador sem gatilho leva
`sem-gatilho`: é o que apodrece. Fecha com `<N> marcadores, <M> sem gatilho.` Só lê e relata, restrita à pasta do
projeto, sem `data/`, `state/` nem `outputs/`; grava o livro só se pedido, em `outputs/` do projeto.

## 5. Mapa do código e chamadores em aberto
[Decisão; ponytail, P4 e P5 — ideias do mapa do código e dos "chamadores em aberto" do ponytail, reescritas como scripts.]
- `python <skill>/scripts/mapa_codigo.py --raiz <raiz> --projeto <p>`: o que já existe, para "reusar primeiro" não
  custar uma busca. Funções, classes e exports de primeiro nível, uma linha por pasta, até `--teto` caracteres (2.000).
  Só dentro de `projects/<p>/`; pula `data/`, `state/`, `outputs/`, testes, pastas geradas e ligações; só mostra
  identificadores. O mapa é dado do projeto, não instrução. Sob demanda, não hook: vira hook só se a medição do §6 mostrar
  ganho.
- `python <skill>/scripts/chamadores_abertos.py --repositorio <pasta> --base <ref>`: no fechamento de cada lote, lista
  a definição que o diff removeu e que ainda é chamada, com `arquivo:linha`. Só lê. É o tipo de defeito que custou
  rodadas na integração da 1.7.10. Regex, não analisador: acusa por nome; confira cada linha antes de agir.

## 6. Como medir (rodada comparável)
[Decisão; ponytail, P8 — método dos benchmarks do ponytail, reescrito; nenhum trecho nem dado de benchmark.] Sem medida, a regra não vira padrão: o ganho que o autor mediu (código novo, sem Bash, em sessões isoladas) pode não se
transferir para o trabalho daqui, que gasta em revisão, suítes e integração, e uma medição independente achou custo
maior de processo em rodadas grandes.
- **Desenho.** De 8 a 10 tarefas reais de código, cada uma numa worktree própria, com o mesmo modelo e o mesmo esforço.
  Braço A sem a regra, braço B com a regra (hook mais plugin). Três execuções por célula, braços alternados por tarefa.
- **Controle limpo.** Ler na transcrição de uma célula de cada braço o que foi injetado: o braço A não pode ter o texto.
- **Métricas.** Tokens e tempo dos subagentes; linhas do diff sem testes (`git diff --numstat`); a última linha do
  unittest; rodadas de revisão até fechar; achados confirmados por revisor; chamadores em aberto (§5) no fechamento.
- **Estatística.** Mediana por tarefa, razão B/A, média geométrica com intervalo bootstrap e teste de sinal. O que não
  couber vai como "não conferido".
- **Revisão enxuta (S1).** `enxuto-revisao` em sombra, ao lado da revisão em leque, num lote: compare tokens e achados
  confirmados. A revisão atual continua sendo o portão até o titular decidir. **Mapa (P4).** Meça o braço B com e sem
  `mapa_codigo.py` antes de virar hook.
- **Custo.** A rodada gasta chamadas de modelo: o teto é decisão do titular, antes de começar.
- **Resultado da primeira rodada (P8, 09/11/2026).** O titular aprovou uma versão menor: 6 tarefas de código da lista de
  pendências, 2 execuções por célula, Sonnet com esforço médio, 24 rodadas (cerca de 2,9 milhões de tokens de
  subagente, dentro do teto de 4% da cota semanal), com a regra entrando pelo pedido e não pelo hook. Razão B/A (com a regra sobre
  sem a regra), média geométrica: tokens 0,99 (B menor em 4 de 6; p = 0,69); tempo 0,72 (p = 0,69); linhas de código
  sem testes 0,55 (B menor em 6 de 6; p = 0,03). Em tarefa pequena o custo vem da leitura do código e da rodada de
  testes, não do código escrito, e a regra (uns 700 tokens por sessão) não se pagou. A qualidade ficou mista: numa
  das 12 rodadas com a regra, parte necessária da mudança ficou de fora. Conclusão: diff menor, nenhum ganho de tokens,
  regra **desligada por padrão**; o titular a liga por projeto se preferir diffs menores. É indício, não prova (6
  tarefas pequenas, uma com premissa errada); medir de novo em tarefa maior, com mais de 100 linhas de código novo.

## 7. Limites
- O hook e o plugin só valem depois do preparo do titular (cópia e registro do hook; ficha assinada e canário do
  plugin). Presença no pacote significa preparado, não ativado.
- A regra é ajuda de estilo, não fronteira: não impede nada que as permissões e os guardas do host já não impeçam.
- Mapa e chamadores usam expressões regulares: perdem definição aninhada ou dinâmica e podem acusar uso em comentário.
