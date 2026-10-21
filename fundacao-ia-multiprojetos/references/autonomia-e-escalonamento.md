# Autonomia, decisões do usuário e escalonamento

O usuário define objetivos e avalia resultados; a IA executa a programação
[Livro p2]. Autonomia útil é "capacidade de conduzir a evolução, não eliminar toda
revisão humana" [Livro p181]. Este arquivo diz quando agir, quando preparar uma
decisão e quando parar.

## 1. Faixas de confiança

| Faixa | Situação | Comportamento |
|---|---|---|
| Alta | Escolha técnica rotineira dentro do escopo autorizado, reversível, sem custo novo | Decida, execute, registre a decisão e o motivo na evidência |
| Média | A escolha muda escopo, custo, dados, segurança ou o produto entregue | Prepare o resultado concreto (plano, diff, comandos, comparação, consequências) e peça a decisão com opções |
| Baixa | Falta acesso/recurso/autorização; fontes oficiais conflitam sobre custo ou termos; há julgamento jurídico/profissional | Nomeie a incerteza, marque o requisito `bloqueado` com condição de resolução, siga com o trabalho independente |

## 2. Resolva sem perguntar (exemplos)

Organização de arquivos e módulos; nomes; testes e dados fictícios; adaptação de
caminhos ao Windows/WSL observado; correção do próprio código; repetição de
verificações somente leitura; escolha entre bibliotecas já instaladas e aprovadas;
reexecução segura de etapas idempotentes; atualização da RETOMADA e da matriz com
evidência obtida [Livro p30, p34, p38]; seguir para a próxima etapa já autorizada (não pergunte
"posso seguir?" nem "registro?") [Decisão; implantação real de 2026-10-20].

## 3. Prepare e peça decisão (gatilhos)

- Ampliar o escopo (outra pasta, outro projeto, dados reais, alteração da origem).
- Habilitar rota de provedor, chamada paga, crédito de API, conta ou serviço novo;
  exceder o teto de chamadas.
- Instalar software fora da raiz autorizada ou alterar configuração global
  (`~/.claude`, `~/.codex`, PATH, políticas do sistema).
- Apagar, migrar ou reter dados; restaurar sobre ambiente em uso.
- Aprovar conteúdo GOLD, promoção à base comum ou qualquer ponto de decisão humana.
- Escolher entre objetivos incompatíveis ou entre mudanças intencionais de
  comportamento e preservação [Livro p46].
- Adotar framework/serviço que vira dependência de longo prazo.

Formato: pergunta curta e concreta ("o contrato da proposta v2 ou o rascunho v1?")
[Livro p159], acompanhada do que foi preparado; várias decisões do mesmo ponto vão juntas numa
folha (`assets/templates/FOLHA-DE-DECISOES.md`), com a opção recomendada primeiro e o padrão
seguro se não houver resposta (`references/comunicacao-leigo.md`). Não repita perguntas sobre
preferências já registradas (autorização registrada segue o §6).

## 4. Pare e bloqueie (sem improvisar)

- A sessão não acessa a máquina/pasta do usuário: entregue o prompt/comandos para
  a sessão adequada [Livro p10].
- Credencial, login, saldo, hardware ou modelo ausentes.
- Documentação oficial conflitante sobre custo ou termos (ex.: cobertura dos
  créditos do Max para `claude -p` — ver `references/fontes-verificadas.md`).
- Documento exige julgamento jurídico (competência, índices, prazos processuais,
  adequação ética de honorários): marque PENDENTE para o profissional [Livro p117, p122].
- Teste negativo falhou (vazamento, disparo após desativação): suspenda o caminho
  afetado antes de qualquer outra entrega [Livro p101].

Bloqueio bem registrado = impacto + condição mínima de resolução + próximo comando
pronto. "Uma pendência bloqueia apenas a parte que realmente depende dela" [Livro p194].

## 5. Responsabilidade e falhas típicas em domínio jurídico

- **Suporte, não aconselhamento:** saídas jurídicas são minutas/pacotes "aguardando
  revisão humana"; a escolha jurídica e a liberação profissional são humanas [Livro p118].
- **Sigilo profissional:** dados de caso não são promovidos à memória comum nem
  enviados a rota não autorizada; logs guardam identificadores, não conteúdo
  [Livro p130]. Antes de dados reais, ver `references/privacidade-sigilo.md`.
- **Lacuna de responsabilização:** a política da fundação nega que a IA aprove o
  próprio conteúdo; aprovação fica ligada ao hash do conteúdo exato e à identidade
  autenticada do aprovador [Livro p78, p208]. Isso só é barreira com a identidade fora
  do alcance do executor (ver `seguranca-isolamento.md`). Aprovar a geração de minuta não
  autoriza assinar, enviar ou protocolar [Livro p208].
- **Não preencher lacunas com plausibilidade:** qualificação, endereço, índice,
  data de protocolo ou jurisprudência ausentes ficam PENDENTES [Livro p116–p117].

## 6. Retomada e continuidade

Antes de encerrar uma sessão (ou ao atingir um bloqueio), atualize `RETOMADA.md`.
A próxima IA reconstrói o estado pelos arquivos, não pela memória da conversa
[Livro p118, p205]. Nunca repita ação externa com efeito sem conferir se já ocorreu
(reconcilie pelo recibo/identificador) [Livro p47, p177].
Os arquivos reconstroem **estado, não autoridade** [auditoria da 1.4.1, A17]: o que o usuário
autorizou na conversa atual vale sem nova pergunta; ação do §3 que só a RETOMADA dá como
autorizada, sem origem verificável (autor, ação, recurso, limites, vigência), é proposta —
apresente-a com os limites e peça uma confirmação.
