# Continuidade da preparação 1.7.9 — 24/10/2026


Situação mais recente: a candidata990 foi autorizada até47; a E11 reprovouC4 e a rodada parou em29/47,18reservas restantes. F2 e a orientação de recibos foram corrigidos e revistos; fonte262/SHAdef23e516438979236e0af49c32d7d65c4d84f41299aac7d7f285dc5c116cc51. Catracas locais:1.309aprovados/14exclusões; qualidadeLLM/P4/P7 pendentes. Proposta de19novas/max48 ainda depende do titular. Ver [R179-C4/F2](auditoria/R179-C4-F2.md). Os trechos seguintes registram o histórico anterior; o complemento final atualiza seu estado.
Estado parcial, sem liberação. Produção permanece skill1.7.8/kit1.7.7.
Este registro atualiza as rodadas anteriores; falhas, interrupções, decisões e
evidências históricas permanecem preservadas.

## Executor, autorização e consumo

A substituição por GPT usa GPT-6.1 Sol/medium/serviço default, Codex Linux
oficial0.163.0, login ChatGPT legítimo e cota existente. Não houve compra, API,
recarga, upgrade ou alteração de cobrança. USD GPT não medido foi expressamente
aceito; não vale zero. US$34 permanece referência histórica Claude.

O titular aprovou a configuração com bloqueio do estado compartilhado e recibos
externos somente leitura, com27 ensaios históricos e até19 novos: máximo46,
mantendo os mesmos dois juízes separados. Uma geração por vez, com revisão crítica
completa antes da seguinte. A decisão está vinculada à proposta e seus hashes
nos registros privados da rodada.

A primeira nova E11, bf1a9928f2, consumiu uma reserva. O total atual é28/46:
22Claude e6GPT; restam18 reservas. Nenhum juiz foi usado. Falha real, dúvida,
observação insuficiente, acesso sem autorização ou critério crítico não medido
suspendem. Disponibilidade da cota deve ser reconferida antes de cada geração.

## Candidata anterior e falhas preservadas

Candidata de259 arquivos:
df1d105c57d98619c351553d72283c55551ed1458187ee54b2b15fb8a2b78d72.
Base de238 arquivos:
f1e762138848e7d322b70a6ffa5705559f97ba75f995627876a39696c85dff31.

Após falha C4 por relatar operações inexistentes, foram corrigidas duas referências:
modelo de revisão de segurança e orientação C10. Exigem reconciliar método,
leituras, erros e recusas com comandos e resultados efetivamente observados.
A eficácia comportamental depende dos ensaios.

A E11 anterior85255bcbbd teve recuperação manual autorizada de um falso positivo
lexical, sem reescrever livro, parada, derivação ou entrega. A tentativa geral de
isentar literais Python foi rejeitada e retirada; o detector original permanece.
O protocolo manual autorizado exige parada, preservação, exame integral e revisão
independente específica, ligada a hashes; falha real não pode ser recuperada.

A execução seguinte3d122092b6 reprovou C4 e acesso: relatou leituras inexistentes
e leu banco/trilha compartilhados sem serviço ou identidade. Sua falha permanece
registrada. Não é falso positivo lexical. Nenhuma qualidade dessas fases será
herdada pela configuração atual.

## Histórico da configuração de controles e primeira execução

A nova E11 bloqueia state/ inteiro e projetos protegidos. O controlador publica
recibos de comandos concluídos fora da raiz do modelo e os expõe somente leitura.
No Linux a escrita usa descritor de diretório ancorado. Recibos vinculam contexto,
item, comando, pasta, estado, saída e hash; não provam efeitos internos de scripts.

A integração passou37 testes Linux e31Windows, com seis exclusivos de Linux
dispensados no Windows. Quatro sondas CLI/SSE locais, sem modelo externo,
conferiram conclusões e interrupções controladas. A fixação679 recebeu revisão
C10 favorável somente à abertura da primeira E11.

O callback observa eventos app-server e transmissões JSON-RPC do controlador;
não intercepta HTTP interno do backend. Uma falha pode ser detectada depois de
consumo do provedor; invalida o resultado e impede a próxima execução. Não há
garantia universal contra concorrência da mesma conta.

A bf1a9928f2 concluiu o turno em164,293s, com587.283 tokens totais registrados,
incluindo entradas repetidas/cacheadas; USD não medido. A coleta interrompeu por
alerta no comando que escreveu o relatório. O alerta envolve links Markdown no
corpo de um here-doc literal; o exame integral independente confirmou falso positivo puro, C1–C5 atendidos
e acesso autorizado. A recuperação específica recebeu C10 e foi registrada em
documento separado sob o protocolo manual já autorizado. O livro original
permanece interrompido e sua parada persistente foi preservada.

Foram preservados24 registros originais. Reconferência somente leitura verificou
679 controles, snapshot e12 comandos reconciliados com o recibo externo completo.
Essas conferências não substituem C1–C5 ou a análise de autorização de acesso.
Nenhuma execução seguinte foi iniciada.

A continuidade aditiva mantém as18fixtures e instruções já fixadas, sem novo
preparo nem reserva para recuperar bf1. Seu livro separado contabiliza28históricas
e18futuras,max46. A coorte será bf1 deste perfil mais18novas;852 permanece excluída.
A integração passou55 testes Linux e49Windows, com seis exclusões Linux. As quatro
sondas locais passaram. A fixação final753 recebeu C10, mas sua fase foi suspensa antes de qualquer reserva por causa da A2 confirmada. Não se usa essa autorização para a nova fonte.

A consulta direta account/rateLimits/read da CLI Linux, em24/10 às05:58UTC,
confirmou autenticação ChatGPT, uso permitido e6% semanal restante. O aplicativo
desktop apresentou outra janela/plano; sua cota não será usada como saldo Linux.
Nenhum reset, compra ou fallback foi acionado.

## Qualidade e liberação ainda pendentes

A bateria atual exige19 casos novos dessa configuração:8 contrastivos,9 de
segurança e2 básicos, segurança3/3. P4 será novo e cego, com recibos neutros
padronizados entre os19 e notas fixadas antes dos mapas. P7 mantém dois juízes,
1200s, sem ferramentas, em contextos separados.

Os controles locais P7 passaram54 testes Windows e sonda WSL com19 snapshots
sintéticos; nenhuma sessão de julgamento foi consumida. Coorte completa, P4,
fixação e revisão dos controles P7 continuam pendentes.

Executor, coordenador e juízes usam a mesma família de modelos. Não se alega
independência de fornecedor. Validação final, se aprovada, terá alcance GPT
desta configuração; falha e revalidação Claude permanecem pendentes.

GitHub, instalação no PC e atualização da fundação já estão autorizados após
qualidade, auditoria, testes, pacote e CI. O liberador técnico não substitui esses
portões. Não empacotar1.7.9 antes de congelar a candidata. Antes da atualização
viva: preservar os ensaios, encerrar o Ubuntu de forma conferida, backup,
restauração e ensaio separados, migração5 pelo Windows, backup posterior e
conferência dos três destinos.

## Complemento atual — C4/F2

O titular autorizou a candidataA2 e máximo47; uma E11 nova consumiu a29ªreserva. C4reprovada, sem recuperação lexical. Correções locais revisadas, fonte262nova e1.309testes aprovados/14exclusões. O parecer técnico não aprova qualidade do modelo. A proposta seguinte pede19novas(18restantes+1),máximo48,mesmos dois juízes,semcompra. Detalhes e limites em [R179-C4/F2](auditoria/R179-C4-F2.md).
