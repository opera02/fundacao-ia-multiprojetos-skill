# Mudanças da 1.7.10.1

Versão: 1.7.10.1 · Anterior: 1.7.10 · Registro: 2026-11-02, correção pedida pelo titular ("Um caminho na fundação para
aplicar a ficha de aberturas do criador-de-peticoes com o canário false/null, sob um aceite de risco assinado por mim.
A forma, a versão e os testes ficam a seu critério"). O kit continua 1.7.10. Escopo, decisão e diagnóstico: pastas
`outputs/inicio-1.7.10.1/` e `outputs/inicio-1.7.11/` do projeto fundacao-de-ia da fundação (fora desta árvore);
revisão de segurança: `entrega/auditoria/REVISAO-SEGURANCA-1.7.10.1.md`.

## Mudanças

| # | Componente | O que mudou | Motivo observado (onde) | Efeito observado (onde) | Veredito |
|---|---|---|---|---|---|
| M1 | `fundacao-ia-multiprojetos/assets/host/preparo_host.py` e `assets/host/wsl/preparar-wsl.sh` | o relatório real do canário com false ou null é instalado como revogação; o portão expõe o reprovado; a ficha vale com ele só sob o aceite de risco do projeto, conferido e fixado no hashes.json, e o lançador recusa o aceite vencido ou outro relatório | o canário real de 02/11/2026 deu false, e nenhuma ficha podia valer; o titular precisa da internet no Criador (DECISAO-007 da fundação) | testes do host nos dois sistemas, com o preparo de ponta a ponta em ensaio no Ubuntu; o aceite real do titular ainda não rodou | sem efeito observado |
| M2 | `fundacao-ia-multiprojetos/assets/host/fundacao_titular.py` | comando `aceitar-risco`: o aceite montado só com código fixo a partir do relatório, mostrado, confirmado pelo nome do projeto e assinado no namespace da ficha, com esquema próprio | a assinatura tinha de ser do titular, fora do alcance da sessão (pedido de 02/11/2026) | testes com o ssh-keygen do sistema e chaves de ensaio: a ficha não serve de aceite nem o aceite de ficha; outra chave, outro namespace, aceite alterado, de outro relatório ou vencido não valem | ajudou |
| M3 | `fundacao-ia-multiprojetos/scripts/tests/test_aceite_risco_canario.py`, `test_host_projeto_canario.py`, `test_host_wsl.py` e `test_fundacao_titular.py` | teste novo do aceite; os dois testes que esperavam a recusa do relatório reprovado passam a esperar a revogação (mudança de critério pedida pelo titular); a superfície do parser da ferramenta ganha o comando novo | o comportamento mudou de propósito | os testes novos e os ajustados passam no Windows e no Ubuntu | ajudou |
| M4 | `fundacao-ia-multiprojetos/scripts/tests/test_integ_fluxob_1710_importar.py` e `test_importar.py` | os testes tiram a FUNDACAO_RAIZ do ambiente antes de chamar o importador no próprio processo | desde o preparo do Windows de 02/11/2026, as sessões da raiz recebem a FUNDACAO_RAIZ, e quatro testes falhavam fora da CI | os quatro passam | ajudou |
| M5 | `fundacao-ia-multiprojetos/assets/templates/CHECKLIST-PROJETO.md` e `references/` | o passo do aceite de risco no checklist; a correção 1.7.10.1; segurança §8 com a revogação e o aceite; fluxos A e C; fontes verificadas com os plugins embutidos da 2.1.302 e as sondas recusadas no canário de 02/11 | os textos diziam que o relatório reprovado não se instala e que nenhuma ficha vale sem o canário aprovado | o verificador de referências e o orçamento do texto passam; o SKILL.md muda só a versão | ajudou |
| M6 | `entrega/licoes.py` | aceita a versão de quatro números (correção de uma versão liberada) | a correção ficou 1.7.10.1, para os textos que dizem "1.7.11" continuarem certos | teste novo da ordem das versões | ajudou |
| M7 | `fundacao-ia-multiprojetos/assets/host/preparo_host.py` e `assets/host/fundacao_titular.py` | correções da revisão de segurança da versão: a versão do aceite com o piso `maior-versao` na área (ACE-1), o aviso do aceite na tela da ficha (ACE-2) e o relatório recusado dentro da raiz ou num disco do Windows (ACE-3) | a revisão independente da diferença achou um aceite antigo voltando pela caixa de entrada, a tela da ficha incompleta e o relatório aceito onde a sessão grava | testes novos dos três, nos dois sistemas | ajudou |

## O que a versão traz

- Com o canário reprovado, a ficha de aberturas de um projeto vale se o titular assinar o aceite de risco daquele
  projeto e daquele relatório (até 180 dias). O isolamento continua lógico; os outros projetos continuam fechados.
- O relatório real reprovado passa a revogar o aprovado da mesma versão do Claude Code (o CAN-2 da 1.7.10, na direção
  do ramo do lote B).
- O registro, para a 1.7.11, de por que o canário de 02/11/2026 não mediu nada e de onde vêm os três plugins.

## Estado da liberação e limites conhecidos

- O aceite não confina nada: com a raiz no disco do Windows visto pelo Ubuntu, o isolamento entre projetos é lógico, com
  o risco de persistência pela pasta do Windows (segurança §8.1).
- O canário que mede de fato (sondas sem variável, plugins embutidos por versão), o lote B e a CI pública verde ficam
  para a 1.7.11. A CI pública desta versão roda com os mesmos testes dependentes das máquinas do GitHub da 1.7.10.
- O aceite real, a ficha real do Criador e o preparo real do titular ainda não rodaram.
- A revisão de segurança da versão deixou o R17101-ACE-4 parcial, de severidade baixa. A versão nova do aceite ainda
  conta a de qualquer JSON assinado no namespace da ficha. Assim, uma ficha que o titular assinasse com a versão 999999,
  copiada pela sessão para o lugar do aceite, faria a ferramenta recusar um aceite novo. Isso não abre nada sem o
  titular. Na forma do Windows, o espelho da raiz também conta. Para a 1.7.11: contar só o aceite deste projeto, com o
  esquema dele, e ignorar o valor que levaria ao teto.

## Lições

### L1 — A prova de que um comando rodou não pode depender de variável do shell
- Gatilho: um ensaio automático abre sessões `claude -p` e precisa provar que cada comando rodou e com que código.
- Lição: no modo sem ninguém para aprovar, comando com variável é recusado antes de rodar; faça o marcador sem `$` (um executor fixo que imprime o código) e guarde no relatório o motivo de cada recusa, para o `nao_medido` se explicar sozinho.
- Evidência: M5; `fundacao-ia-multiprojetos/references/fontes-verificadas.md`, conferência da 1.7.10.1; o canário de 02/11/2026 teve 28 de 29 chamadas recusadas pelo `$?` do marcador e só disse `nao_medido`.
- Confiança: alta

### L2 — Teste que roda a ferramenta no próprio processo limpa o ambiente da sessão
- Gatilho: o ambiente das sessões muda (o preparo do host passa a pôr variáveis nelas) e a suíte roda numa dessas sessões.
- Lição: além do ambiente dos subprocessos, o teste que chama `main()` no próprio processo tira as variáveis da fundação viva; rode a suíte numa sessão da raiz antes de liberar, não só na CI.
- Evidência: M4; `fundacao-ia-multiprojetos/scripts/tests/test_integ_fluxob_1710_importar.py` e `fundacao-ia-multiprojetos/scripts/tests/test_importar.py`; quatro testes falharam por causa da FUNDACAO_RAIZ do perfil do Windows de 02/11/2026, que a CI não tem.
- Confiança: alta
