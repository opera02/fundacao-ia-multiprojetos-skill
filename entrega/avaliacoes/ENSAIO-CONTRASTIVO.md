# Ensaio contrastivo de mudança de instrução

> Modelo para decidir se uma regra nova funciona antes de dá-la como "funcionando": regra da skill, do `AGENTS.md`,
> das `INSTRUCOES.md` de um projeto ou de uma skill de projeto. [Decisão; harness2, P4] Método adaptado de Harness²
> (arXiv:2610.14224, github.com/google-research/harness2, commit 1cfe254, Apache-2.0); texto próprio.
> Rodar o ensaio chama modelo e gasta cota: só com autorização do titular, com teto no livro-caixa. As ferramentas
> citadas estão em `fundacao-ia-multiprojetos/evals/` (fora do pacote instalável). Numa fundação, copie este modelo
> para o projeto e use-o no C6 para mudanças de instrução.

## 1. O que se compara

| Campo | Preencher |
|---|---|
| Mudança | o trecho novo (arquivo e seção) e o motivo observado (avaliação, rastro, achado ou teste) |
| Base | o texto anterior: pasta ou commit e o SHA-256 da skill (o `livro_avaliacoes.py abrir` calcula) |
| Candidato | o texto novo: pasta ou commit e o SHA-256 da skill |
| Amostra fixa | as avaliações usadas, iguais nos dois braços: o caso de treino que motivou a mudança e ao menos um **caso de teste** (`papel: "teste"` no `evals.json`: nunca serviu para escrever regra) |
| k por braço | execuções de cada braço; k = 1 é **teste de fumaça** e não separa efeito de ruído |
| Teto do livro | partidas autorizadas (a interrompida conta), citação literal da autorização e o SHA-256 do livro (`conferir`) |

Commit em vez de pasta: extraia a árvore numa pasta (`git worktree add` ou `git archive`) e passe a pasta.

## 2. Preparo e execução

1. `python livro_avaliacoes.py abrir --livro <pasta> --autorizacao "<palavras do titular>" --data <iso> --teto <n>
   --modelo-esperado <id> --braco base=<pasta> --braco candidato=<pasta>` (`--modelo-auxiliar <id>` só se o host
   usar um modelo pequeno por conta própria: ele é aceito no `result`, nunca nas respostas).
2. `python preparar_avaliacoes.py --workspace <dir> --so <ids> --execucoes <k> --livro <pasta> --simular` mostra o
   plano e o teto restante; sem `--simular`, prepara. Os braços são idênticos salvo a skill: o `isolamento.json` traz
   a impressão de cada ambiente e para se ela diferir.
3. Para cada pedido do `prompts.json`: `livro_avaliacoes.py iniciar --iteracao <bancada> --execucao <id do pedido>`
   (a partida fica amarrada à execução; recusa se a cópia da skill ou o ambiente não forem os do preparo); rodar com
   as ferramentas de `ferramentas_negadas` negadas na própria chamada; guardar a transcrição em
   `<registro>/trace.jsonl`; `livro_avaliacoes.py fechar` (modelo, modelos que responderam, custo informado pelo
   cliente, turnos e duração vêm do rastro; o SHA-256 do rastro fica na partida; a cópia da skill é reconferida).
   Execução sem partida concluída que confira não entra no cegamento nem conta no resumo (revisão de segurança da
   1.7.7, R177-VAL-08: com teto 1 e uma partida, três execuções tinham sido cegadas e contadas), e uma partida dá
   lastro a uma execução só: a amarrada a ela no `iniciar`.
4. `python verificar_execucoes.py --iteracao <bancada>`: fatos de todas as execuções, inclusive `acesso_ao_gabarito`
   (execução "contaminada" não pode ser aprovada).

## 3. Nota cega

1. `python cegar.py cegar --iteracao <bancada> --livro <pasta> --destino <pasta cega>`: as saídas vão para
   `<pasta cega>/<avaliação>-<letra>/`, numa raiz separada — nova ou vazia, fora da bancada, do workspace e do pai
   dele, da área do executor, do livro e do repositório, nem ao lado dele; o mapa fica no livro. Na bancada, os
   originais em `eval-*/<braço>/run-*/outputs` e o `prompts.json` revelam o mapa pelo SHA-256 das cópias (revisão
   de segurança da 1.7.7, R177-VAL-07).
2. Entregue a quem dá as notas só a pasta cega (copiada ou compactada; nunca a bancada, a área nem o livro). As notas
   vão em `<pasta cega>/notas.json`, sem abrir o mapa (uma por asserção: `true`, `false` ou `"nao_medido"`).
3. `python cegar.py notas ...` grava o hash da folha no livro; `python cegar.py revelar ...` só depois disso, e grava a
   nota de cada execução (`grading.json`).
4. `python resumo_k.py --iteracao <bancada> --livro <pasta>`: pass@k e pass^k, só com as execuções que têm partida
   concluída no livro; avaliação de segurança só passa com pass^k.

## 4. Ponto de divergência

Para cada caso da amostra, leia as trajetórias dos dois braços e anote o primeiro momento em que os comportamentos
se separam: a chamada, o arquivo lido, a decisão tomada. Cite o evento do rastro. Mudança que não se liga a um
momento da trajetória é especulação. Mesmo com a nota empatada, a divergência dá sinal.

| Caso | Execução | Ponto de divergência (evento do rastro) | O que o candidato fez de diferente |
|---|---|---|---|
| | | | |

## 5. Veredito por mudança

| Mudança | Efeito observado (onde) | Veredito |
|---|---|---|
| | | ajudou · piorou · sem efeito observado · confundido |

- Com k = 1, com várias mudanças juntas ou sem contraste mecânico (fato do verificador ou asserção que separa os
  braços), o veredito padrão é **confundido**.
- Execução que **não entregou nada** torna a mudança insegura: não conta como "ajudou".
- O que se repete nas k execuções é real; um defeito em uma delas é ruído. Concordância entre braços ou entre
  avaliadores é apoio, não prova.
- No caso de teste, a regra precisa mostrar efeito sem que o caso tenha servido para escrevê-la. Só no caso de
  treino, o resultado é nota de treino.

## 6. Decisão

| Decisão | Quando |
|---|---|
| adotar | a mudança ajudou no caso de teste e não piorou nenhum caso da amostra |
| manter o texto anterior | sem efeito observado ou confundido (resposta válida: a mudança não se pagou) |
| revisar | piorou algo, ou ajudou só no caso de treino |

Quem decide é o titular, pela conversa e pelos portões da liberação. Registre a decisão, o rótulo das partidas e o
SHA-256 do livro no `AVALIACOES.md` (ou nas evidências do projeto).
