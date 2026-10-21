# Comunicação com o titular leigo

[Decisão; auditoria da implantação real de 2026-10-19/20: 66 intervenções do titular em ~23 h,
19 evitáveis — "siga para o B2", "registre", "em que etapa estamos?" — e 10 causadas por
instruções que não se executavam como escritas.] Vale para toda parada e todo relato de
progresso, salvo quando o usuário pedir o detalhe técnico.

## 1. Não pare sem motivo

- Encadeie as etapas autorizadas. "Posso seguir?", "registro o resultado?" e "comece a
  próxima" não são decisões do usuário: o que `autonomia-e-escalonamento.md` §2 manda resolver
  sem perguntar (RETOMADA, matriz, evidências, testes, próxima etapa autorizada) segue sozinho.
- Pare só em três casos: portão de aprovação do fluxo (fluxo B: dois portões; fluxo A: o
  formulário inicial e as ações do titular), decisão da faixa média (§3 da autonomia) e
  bloqueio (§4). Junte o que puder num único momento.
- Pergunta com várias decisões vira **uma** folha (`assets/templates/FOLHA-DE-DECISOES.md`),
  com a opção recomendada primeiro e "se não responder: <padrão seguro>" em cada item.

## 2. Cartão de parada (até ~120 palavras)

1. **Onde estamos:** "Etapa X de Y — <nome simples>" e o que ficou pronto, com o resultado
   concreto (número, arquivo, teste) e não o processo.
2. **O que depende de você — uma coisa:** a ação ou decisão, a opção recomendada primeiro e a
   consequência de cada opção em uma linha; tempo estimado quando for uma tarefa.
3. **Depois:** o que a IA faz sozinha em seguida e o que acontece se não houver resposta
   (segue no que não depende dela, ou espera).

Códigos (R51, B3, M2) só entre parênteses, depois do nome simples. Nome de projeto parecido
com "fundação": escreva sempre "o projeto <nome>" × "a fundação".

## 3. Comando que o titular precisa rodar

- Um bloco por comando, pronto para copiar, **no shell em que ele vai rodar**: PowerShell
  usa `E:\pasta`; o bash do WSL usa `/mnt/e/pasta`. Diga onde abrir (PowerShell comum ou como
  administrador; terminal do Ubuntu) e o que deve aparecer no fim.
- Nunca dentro de uma pergunta ("rodou o /reset como administrador?"): primeiro o comando e o
  resultado esperado; a pergunta, se houver, vem depois.
- Mais de dois passos seguidos → um script único da skill (versionado, com hash conferível),
  não uma lista para digitar.
- Peça a saída só quando ela decidir algo; prefira que o script grave o resultado num arquivo
  que a IA lê.

## 4. Linguagem

Português simples; termo técnico com explicação curta na primeira vez; resultado antes do
processo; números com unidade. Simulação sempre rotulada; "não medido" nunca vira zero;
"pronto" só com a evidência citada (`principios-e-evidencias.md`).

## 5. Exemplos

Ruim: "Rodou o /reset no allowed_signers como administrador? Se sim, me passe a saída do icacls."

Bom: "Etapa 3 de 6 — proteção das assinaturas. Falta um passo seu (1 minuto): abra o
PowerShell **como administrador** e rode o comando abaixo; no fim deve aparecer `protegida`.
Depois eu sigo sozinho para a etapa 4 (backup)."

Ruim: "B2 concluído. Posso iniciar o B3?"

Bom: (nenhuma mensagem: o B3 começa sozinho; o titular vê o mapa, a compatibilidade e o plano
juntos no portão 1, com a folha de decisões.)
