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
| 6 | Execução isolada no SO e host em uso: comandos do agente e processos que a fundação inicia não leem arquivos de outros projetos nem segredos, e CLIs de provedor também não leem `state/` — prova negativa com canário e falha fechada se o mecanismo faltar. Ex.: Claude Code no Windows, WSL2 com `sandbox.failIfUnavailable: true` (o nativo roda comandos SEM sandbox); outro host, o equivalente conferido na versão instalada. Presença do mecanismo não prova isolamento | executor + titular | | pendente |
| 7 | Segredos ilegíveis e escrita só no projeto autenticado, com prova negativa no host em uso. Ex.: Claude Code, `permissions.deny` + PreToolUse (`guarda_caminho.py`); outro host, o controle equivalente conferido na versão instalada | executor | | pendente |
| 8 | Backup consistente fora da máquina, com restauração ensaiada e registro de retiradas reaplicável | executor | | pendente |
| 9 | ACL por cliente/caso ("muralha ética"): caso A não recupera caso B — teste negativo com marcadores | executor | | pendente |
| 10 | Componentes externos (skills, MCP, plugins, hooks, pacotes Python) fixados por versão e hash, com revisão de diff | executor | | pendente |
| 11 | Identidade das operações vinda do lançador; separação de papéis com barreira (sessão do agente em outra conta do SO, sem escrita em `state/`, ou aprovação com credencial do titular fora do alcance do executor) ou registrada como só lógica da política (`references/seguranca-isolamento.md` §2) | titular | | pendente |

Se qualquer item estiver pendente: continue somente com dados fictícios e mantenha
o requisito correspondente como `bloqueado`, com a condição de resolução.
