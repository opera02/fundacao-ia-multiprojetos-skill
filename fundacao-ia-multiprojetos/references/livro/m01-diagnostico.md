# Módulo 01 — Diagnóstico e decisões (A01–A04B, p8–27)

## Ideia central
Antes de construir, reduza a incerteza que afeta as próximas decisões: saiba o que
existe, o que funciona, quem pode acessar o quê e quanto custa — com evidência, sem
alterar nada — e escolha a arquitetura por critérios e protótipos, não por preferência.

## Frameworks do livro
- **Quatro níveis de evidência** (A01 p8): documentado · código presente · executado ·
  validado. Use para qualificar cada frase do relatório.
- **Cinco tipos de conteúdo** (A02 p12): regra de domínio · configuração · programa ·
  plano · teste. A regra de domínio sobrevive à troca de framework.
- **Três modalidades de trabalho** (A03 p16): sessão assistida (conta/modalidade e tarefa
  observadas) · integração programática (chamada real, identidade, consumo) ·
  transferência manual (origem e conteúdo transferidos).
- **Equação de custo previsto** (A03 p17): entrada sem cache × tarifa + entrada com cache
  × tarifa aplicável + saída × tarifa + ferramentas/serviços auxiliares (unidades
  coerentes; sem dupla contagem).
- **Três estratégias** (A04 p21): manter · reformular por partes (hipótese de referência
  do livro para o OpenSquad) · substituir a execução.
- **Matriz de decisão sem notas inventadas** (A04 p21): pesos antes; escala 0–4;
  "não investigado" separado de 0; pesos pedagógicos 25/20/15/15/10/10/5.
- **Protótipo discriminante** (A04B p25): normal · falha após efeito · troca de adaptador
  · projeto sem acesso — mesmo cenário em duas abordagens.

## Conceitos-chave
Manifesto de hashes (identifica conteúdo, não é backup) · estado do Git (não representa
bancos, segredos, serviços) · dependência declarada × instalação detectada ×
comportamento verificado · mapa de funcionamento · divergência de contrato produtor ×
consumidor · autorização aplicada fora do modelo · orçamento = dinheiro + capacidade.

## Modelos mentais
- Pense no relatório como "frase → registro concreto que a sustenta".
- Use "preservar · adaptar · substituir · investigar" por componente, nunca "reescrever tudo".
- Trate assinatura, CLI, SDK e API como portas diferentes, cada uma com sua evidência.
- Uma arquitetura é um acordo sobre quem faz o quê por quais interfaces (núcleo ·
  adaptadores · projetos · casos).

## Antipadrões (dos exercícios)
- Concluir "assinatura autenticada e integração funcionando" de `claude --version` (p11).
- "Custo da tarefa: R$ 0" por usar a assinatura (p19) → "sem cobrança adicional observada",
  com consumo, duração e limites.
- Unificar três cópias de exportador sem saber se a diferença é legítima (p15).
- Agente importando a biblioteca de um único provedor "basta trocar o nome do modelo"
  → teste: segunda implementação do contrato com formatos/erros diferentes (p23).
- Protótipo mais rápido porque não grava estado declarado superior (p27).
- Estrelas do GitHub como prova de adequação; licença permissiva ≠ serviço gratuito (p21, p24).

## Exemplo trabalhado (A02 p12–13)
Fluxo de petições: solicitação → triagem → pesquisa → redação → revisão → exportação;
para cada passagem, o contrato e a pergunta de inspeção ("quem fixa o escopo autorizado?",
"uma hipótese pode virar fato?", "o revisor confere a origem?", "quem impede saída
prematura?"). Divergência didática: manifesto com `agents` como objetos (`id`, `file`)
× leitor que espera lista de strings — solução: formato canônico, validador e adaptador
do legado, sem corrigir a origem só por observar.

## Verificações de aceite derivadas
- A01: itens essenciais respondidos ou bloqueios precisos; três achados sustentados; nada
  alterado fora dos relatórios (p10–11).
- A02: toda etapa com executor ou lacuna; todo candidato à migração com evidência; toda
  hipótese com teste decisivo (p14).
- A03: cada acesso com evidência; cada custo com tarifa/modalidade ou lacuna; integração
  não executada continua assim identificada (p18).
- A04/A04B: fontes primárias datadas; mesmo cenário nas duas abordagens; teste capaz de
  refutar a recomendação; se só uma for executável, comparação documental + experimento
  pendente (p23, p26).

## Adaptação para a skill
Aulas → etapas A1–A3 do Fluxo A e B1–B3 do Fluxo B. "Registro de aprendizagem" e
"devolva ao tutor" → relatório ao usuário com a frase mais forte, a evidência e a
lacuna principal. CaixaSim como software de estudo → cenário de aceite substituível
por software do usuário com evidências equivalentes (A04 p22).

## Conecta com
`../fluxo-a-implantar.md` (A1–A3), `../fluxo-b-adaptar.md` (B1–B3),
`../capacidades/01-orquestracao.md`, `../capacidades/03-provedores-modelos.md`.
