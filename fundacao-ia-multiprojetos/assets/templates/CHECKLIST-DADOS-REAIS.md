# Checklist antes de usar dados reais (clientes, casos, pessoas)

Nenhum item abaixo é preenchido pela IA como "feito" sem evidência datada.
Itens jurídicos são pontos de verificação para o profissional responsável — a
skill não emite parecer (fonte: proposta 3.0 §6 e §3.12; ver
`references/privacidade-sigilo.md`).

| # | Verificação | Responsável | Evidência (data) | Estado |
|---|---|---|---|---|
| 1 | Treinamento com dados desligado em TODAS as contas/planos usados (inclusive a opção de ambientes do Codex), conferido nas telas oficiais | titular | | pendente |
| 2 | Rota para conteúdo sigiloso definida (comercial/API sem treino por padrão, ou modelo local); rota de assinatura NÃO exposta a outros usuários | titular | | pendente |
| 3 | Base legal, finalidade e necessidade por operação registradas; avaliação de impacto quando cabível | profissional responsável | | pendente |
| 4 | Transferência internacional: mecanismo de cada provedor conferido | profissional responsável | | pendente |
| 5 | Cliente informado sobre o uso de IA quando exigido pelas regras profissionais aplicáveis | profissional responsável | | pendente |
| 6 | Sandbox ativo em WSL2 com falha obrigatória se indisponível (Windows nativo roda comandos SEM sandbox) | executor + titular | | pendente |
| 7 | `permissions.deny` para segredos e hook PreToolUse negando escrita fora do projeto autenticado, com prova negativa | executor | | pendente |
| 8 | Backup consistente fora da máquina, com restauração ensaiada e registro de retiradas reaplicável | executor | | pendente |
| 9 | ACL por cliente/caso ("muralha ética"): caso A não recupera caso B — teste negativo com marcadores | executor | | pendente |
| 10 | Componentes externos (skills, MCP, plugins, hooks) fixados por versão e hash, com revisão de diff | executor | | pendente |

Se qualquer item estiver pendente: continue somente com dados fictícios e mantenha
o requisito correspondente como `bloqueado`, com a condição de resolução.
