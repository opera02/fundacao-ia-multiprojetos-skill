# Revisão de segurança — <skill/fundação/projeto> — <versão anterior>..<versão nova>

> Relatório de trabalho PRIVADO, somente leitura: a revisão não altera nada na árvore revisada e o relatório fica
> fora dela (ex.: `entrega/auditoria/` da árvore de desenvolvimento, gravado com hash). Redija: sem credenciais,
> dados pessoais, caminhos internos de clientes nem trechos de caso. Traduzido e adaptado do modelo de revisão de
> segurança do vibe-coding-toolkit (MIT; análise de 21/10/2026; aviso de copyright e licença em
> `<skill>/AVISOS-DE-TERCEIROS.md`). Apague os campos que não usar.

## Escopo

- Revisor, cliente e data (outro contexto; se for o mesmo provedor do autor, diga):
- Modo: repositório inteiro | diff exato (base e head por commit; comparação ponta a ponta ou desde a base comum)
- Diferença revisada (base..head, por commit): `<base>..<head>` — na liberação da skill, a base é o commit testado da
  versão anterior (ou um anterior a ele) e, depois do head, só podem mudar arquivos que não são código
- Camadas incluídas: commits, mudanças não commitadas, arquivos não rastreados (cada uma à parte):
- Autorização assumida e exclusões (o que NÃO foi lido, como dados de projetos e state/):
- Ativos, entradas, identidades e papéis, projetos e casos, fronteiras de confiança:
- Suposições sobre o ambiente que precisam de confirmação:

## Cobertura e evidência

- Caminhos revisados e excluídos (com o motivo):
- Ferramentas e referências usadas, com versão:
- Comandos e testes rodados, com o isolamento e o resultado (estático · simulado · execução real):
- Árvore revisada inalterada: SHA-256 antes = depois (manifesto) e nenhum efeito na fundação:

## Achados

Repita por achado comprovado ou hipótese rotulada. Achado sem cenário de falha concreto é palpite: vai para
"Pendências". Se não houver achados, escreva que nenhum foi comprovado neste escopo.

### <ID> — <título>

- Severidade (crítica · alta · média · baixa) e por quê:
- Confiança (alta · média · baixa); situação: confirmado | a validar
- Origem: introduzido nesta versão | regressão | preexistente | indeterminado
- Local: arquivo:linha e revisão (ou camada não commitada)
- Evidência redigida e caminho alcançável, da entrada até a operação sensível:
- Quem consegue disparar e com que pré-requisitos (identidade, permissão, arquivo):
- Cenário de falha concreto (a entrada ou o estado que faz quebrar) e impacto:
- Contraevidência considerada; reprodução ou teste, ou a prova que falta:
- Correção estreita proposta e próxima validação:

## Pendências e limites

- Hipóteses não comprovadas e a evidência que falta:
- Endurecimento sugerido (separado dos achados):
- Lacunas de cobertura e próxima validação útil:
- Relatório redigido e guardado em local privado, conferido:

Esta revisão não estabelece que a versão é segura nem certifica conformidade. Achados e confiança valem só para o
escopo e as evidências registrados. Nenhuma correção foi aplicada pela revisão.
