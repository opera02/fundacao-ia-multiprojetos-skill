# Módulo 07 — Projeto jurídico (A22–A25, p115–132)

> Todo o conteúdo deste módulo é **didático e fictício**. Serve para testar o método de
> migração e verificação de fluxos de domínio na fundação. Não é parecer, não define
> honorários reais e não substitui a revisão profissional, que é sempre humana.

## Ideia central
Um fluxo jurídico migrado é aceito quando cada frase material tem fonte identificada ou
ressalva, os números são reconstruíveis por cálculo determinístico, as condições
concordam entre cálculo, proposta e contrato, as lacunas ficam visíveis e a liberação
continua bloqueada até a revisão profissional.

## Caso Estante Aurora — AUR-001 (data de referência factual 20/08/2026)
Consumidora fictícia Lívia Ribeiro comprou estante Aurora (uso residencial) da empresa
fictícia Casa Horizonte Comércio Didático por R$ 1.200,00, frete incluído [Livro p115].
| Doc | Conteúdo |
|---|---|
| D1 | Pedido AUR-104 de 03/08/2026: uma estante, total R$ 1.200,00, Pix integral, entrega até 10/08/2026; aceitação registrada; sem multa |
| D2 | Comprovante simulado: transferência de R$ 1.200,00 em 03/08/2026 vinculada ao pedido |
| D3 | Conversa: 12/08 9h pede cancelamento e devolução integral; 13/08 10h20 vendedora informa indisponibilidade e restituição solicitada, sem data |
| D4 | Declaração de 20/08: não recebeu a estante nem identificou restituição (alegação) |
| D5 | Extrato 03–20/08 sem crédito identificado como devolução (só aquele período/conta) |
Faltam: qualificação, município de domicílio, endereço citável da empresa, procuração,
procedimento e competência, conciliação, data de eventual ajuizamento — **pendências**,
nunca preenchidas por plausibilidade [Livro p115–116].

## A22 — Pacote de petição
Matriz fato · documento · tese a revisar · pedido coerente (p116): compra por R$ 1.200
(D1, D2; oferta vinculante); entrega até 10/08 (D1, D3; descumprimento); restituição
escolhida (D3; CDC art. 35, III); sem crédito até 20/08 (D4, D5; obrigação pendente).
Referências normativas do exercício: CPC arts. 319, 320, 373; CDC arts. 30, 35 e 101, I
[P01, P02 — conferir texto oficial vigente]. Saídas: `caso.json`, `matriz.md`,
`minuta.md`, `pendencias.md`, `revisao.md`, com PENDENTE para competência e
procedimento, qualificação, critérios de atualização e revisão profissional (p117).
Testes: execução normal e **sem D2** (pendência de prova do pagamento; a alegação não
desaparece) (p117–118). Falhas típicas: data da consulta como data dos fatos; página que
não contém o artigo; misturar entrega com restituição; "a ré se recusa definitivamente"
(acrescenta fato; admissível: "a restituição não estava identificada na data de referência") (p118).

## A23 — Honorários (cálculo determinístico com Decimal)
| Atividade | Horas | R$/h | Custo |
|---|---|---|---|
| Entrevista e organização | 1,5 | 80,00 | 120,00 |
| Análise do dossiê | 2,0 | 80,00 | 160,00 |
| Redação da minuta | 3,0 | 80,00 | 240,00 |
| Revisão e entrega | 1,0 | 80,00 | 80,00 |
Trabalho R$ 600,00 + despesas internas R$ 60,00 = custo R$ 660,00 (não reembolsado de
novo). Despesas externas: limite R$ 120,00 com autorização e comprovação, **fora** do
preço. Margem 25%: preço = 660 / (1 − 0,25) = **R$ 880,00**. Markup 25% daria 825
(sobra = 20% do preço) — nomes diferentes, decisões diferentes. Desconto 10%: **R$ 792,00**;
margem cai para ≈ **16,67%** (não se subtrai porcentagem de porcentagem). Êxito de 10%
sobre R$ 1.200 recebidos = R$ 120 em cenário **separado**, não adotado (p119–121).
Código de referência (p120): Decimal, `localcontext().prec = 28`, `quantize(D("0.01"),
ROUND_HALF_UP)`; saída esperada `600.00 660.00 880.00 792.00` e `0.166667`.
Negativos: margem = 100% (denominador zero → rejeitar com mensagem do campo), `"NaN"`,
horas negativas, despesa interna cobrada de novo como reembolso (p122). Exercício:
1.200 − 792 − 35 (despesa externa efetiva) = **R$ 373,00** (usar o limite de 120
confundiria teto com realização) (p123). [3.0 R15.5] Defina **uma** regra de
arredondamento do desconto e importe-a nos fluxos.

## A24 — Proposta
PROP-AUR-01 (21/08/2026, R$ 880,00) → PROP-AUR-02 (22/08/2026, desconto R$ 88,00,
**R$ 792,00**, mesmo escopo; validade fictícia 28/08/2026), baseada em CALC-AUR-02;
sem êxito; despesas externas até R$ 120 fora do desconto (p124). Parcelas:
**R$ 316,80 + R$ 316,80 + R$ 158,40 = R$ 792,00** (assinatura · primeira minuta com
matriz · revisão consolidada) (p125). Regras de consistência: `success_fee.enabled =
false` impede cláusula de êxito; `scope.filing = false` impede "acompanhamento integral";
"R$ 792,00 incluindo todas as despesas" × JSON com reembolso de até R$ 120 → bloquear
(p125–126). Negativo: total 792 com parcelas 352 + 352 + 176 (= 880) → rejeitar (p127).
Reduzir silenciosamente a revisão para compensar o desconto → não (p127). Gerador recebe
só os campos necessários (limitação ao necessário, LGPD) (p125).

## A25 — Contrato
Linha do tempo: PROP-AUR-02 (22/08, válida até 28/08) → evento fictício ACE-AUR-01
(25/08/2026 14h, `simulation: true`, hash **real** do arquivo da proposta) → CONT-AUR-01
(26/08/2026, minuta pedagógica) (p128). Cláusulas: partes (qualificações pendentes),
objeto e entregas, extensão (sem protocolo, representação, audiência, recurso,
negociação), honorários R$ 792,00 e parcelas, despesas (limite R$ 120, sem débito
automático), entradas e programação, confidencialidade e ferramentas, alterações e
encerramento (p129). Testes negativos: inserir "representação em todas as instâncias"
e "autorização irrestrita de compartilhamento" → conflitos apontados; acesso aos anexos
pelo contexto do projeto de software → negado (p131–132). Hash prova integridade dos
bytes, não identidade, poderes ou consentimento (p128). Edição posterior = nova versão.
Estado correto com números certos e cláusulas pendentes: "minuta pendente de revisão";
cada fluxo (petição, honorários, proposta, contrato) exige sua própria evidência (p132).

## Antipadrões
Preencher qualificação/endereço/índice/data por plausibilidade; inventar jurisprudência;
recalcular valores pela redação; "testado" lido como "aprovado juridicamente"; marcar o
projeto inteiro como migrado por um caso fictício.

## Adaptação para a skill
Este módulo vira **cenário de aceite** do Fluxo B (migração de fluxos de domínio) e dos
testes de consistência. [3.0 R15.1–R15.2] Em uso real: fonte única (`caso.json` → DOCX →
PDF), verificador determinístico de citações (artigo na cópia oficial datada, trecho
confere, DV do número CNJ módulo 97; jurisprudência sem fonte oficial = pendente).

## Conecta com
`../fluxo-b-adaptar.md`, `../autonomia-e-escalonamento.md` §5, `../privacidade-sigilo.md`.
