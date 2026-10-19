# Privacidade, sigilo profissional e uso de dados reais

Esta skill **não emite parecer jurídico**. Os pontos abaixo são verificações que o
profissional responsável confirma antes de liberar dados reais. Origem: livro
[Livro p125, p130, p139, P03, P05] e proposta 3.0 (§1 risco 2, §3.12, §6, novo módulo
M04B). Itens marcados **[3.0 — não verificado nesta skill]** vêm do documento de
correções e precisam de conferência nas fontes oficiais antes de uso.

## 1. Regra operacional
Até `assets/templates/CHECKLIST-DADOS-REAIS.md` estar completo com evidências
datadas, use **somente dados fictícios**. Requisitos R55/R56 ficam `bloqueado` com a
condição de resolução correspondente.

## 2. Configuração das contas e rotas (titular)
- Planos de consumo podem usar conversas para treinamento conforme a configuração da
  conta; o titular confere e desliga nas telas oficiais (inclusive a opção de ambientes
  do Codex) e registra a evidência com data (validade sugerida: 90 dias) [3.0 R12.1 —
  não verificado nesta skill; ver fontes citadas na proposta: termos de consumo da
  Anthropic e controles de dados da OpenAI].
- Planos comerciais/API não treinam por padrão segundo a proposta [3.0 — não verificado];
  conteúdo sigiloso usa rota comercial/API ou **modelo local** (`task_routes.sigiloso`
  no seletor de rota).
- Rota de assinatura é pessoal: não a exponha a outros usuários do escritório
  [Verificado 2026-10-18: uso comum do Claude Code × produtos com chave de API].

## 3. Proteção de dados (pontos de verificação)
- Finalidade, necessidade e segurança desde a concepção orientam o desenho: o gerador de
  proposta recebe só os campos necessários, não extratos nem conversas [Livro p125, P03].
- [3.0 R12.2–R12.5 — não verificado nesta skill] Base legal por operação; registro de
  operações; relatório de impacto quando cabível; tratamento de incidentes;
  transferência internacional conforme o mecanismo de cada provedor; direitos do titular
  alcançando índice, vetores, caches, memória e backups (via marcadores de retirada);
  pseudonimização local reversível antes do envio — dado pseudonimizado continua
  pessoal.

## 4. Sigilo profissional e IA na advocacia
- O sigilo alcança fatos conhecidos no exercício da profissão; a arquitetura decide
  quem abre o contrato, que componente recupera anexos e onde ficam versões, registros e
  cópias [Livro p130, P05].
- Dados de caso nunca são promovidos à memória comum só por terem sido usados; logs
  guardam identificadores, não conteúdo [Livro p129–130].
- [3.0 R12.6 — não verificado nesta skill] Recomendação do Conselho Federal da OAB sobre
  IA generativa (supervisão humana, sigilo, informação ao cliente) e regras do Estatuto
  e do Código de Ética citadas na proposta; confira texto oficial vigente.
- [3.0 R12.8] Regulação brasileira de IA: projeto de lei citado na proposta **não é lei**
  na data do documento; acompanhar pela fonte oficial.

## 5. O que a IA executora faz e não faz
Faz: implementa ACL por caso, retiradas propagadas, rotas sigilosas fechadas, logs sem
conteúdo, checklist com campos de evidência, testes negativos com marcadores fictícios.
Não faz: declarar conformidade legal, decidir base legal, informar cliente, alterar
configurações de conta do titular, ou usar dados reais "só para testar".
