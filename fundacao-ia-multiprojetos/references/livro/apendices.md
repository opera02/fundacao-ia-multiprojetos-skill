# Apêndices do livro (A–F e referências, p182–219)

## A — Glossário (p182–186)
Definições operacionais e didáticas; produtos diferentes usam o mesmo nome para
mecanismos distintos — registre a definição adotada, a fonte e a versão. Síntese:
`references/livro/glossario.md`.

## B — Matriz dos 51 requisitos (p187–193)
Treze capacidades obrigatórias → 51 verificações (R01–R51, numeração editorial desta
edição; ao incorporar matriz anterior, preserve os códigos antigos numa coluna de
correspondência). Presença da aula = cobertura pedagógica; conclusão = evidência no
ambiente. Nenhuma linha começa "implementada". Campos do registro, estados e regras de
revisão: `../principios-e-evidencias.md` §3–§4. As provas dos dois projetos atravessam a
matriz: pacote jurídico único (diagnóstico do original, petição, honorários, proposta,
contrato, versões coerentes) e quatro entregas do projeto de software (evidência para
R02, R04, R09, R18, R41, R42) (p193). Requisitos completos: `../requisitos.md`.

## C — Prompts para validar, corrigir e retomar (p194–198)
C1 validar entrega · C2 diagnosticar falha · C3 corrigir dentro de limite · C4 retomar
em outra sessão/provedor · C5 criar outro projeto · C6 atualizar componente
compartilhado · C7 promover para GOLD. Evidências em `evidence/<AULA>/<run_id>/<tipo>/`.
Uma pendência de acesso/custo/decisão bloqueia só a parte que depende dela. Procedimentos
operacionalizados em `../fluxo-c-operar.md`.

## D — Preparar o Windows e o ambiente (p199–203)
- Escolha um ambiente principal: Windows nativo (projeto em pastas Windows, dependências
  funcionam) ou WSL 2 (ferramentas Linux; projeto no sistema de arquivos Linux, não em
  `/mnt/c`; `.venv` não compartilhada) (p199). Claude Code: sandbox só em WSL2
  [Verificado 2026-10-18].
- Terminal × shell × diretório atual × PATH explicam "programa existe mas não é encontrado"
  e "IA criou arquivos no lugar errado" (p199).
- Diagnóstico sem instalar (A01): `Get-Location`, `$PSVersionTable.PSVersion`,
  `Get-Command git,python,py,pymanager,node,npm -All`, `Get-Command claude,codex,wsl -All`,
  `wsl --list --verbose` (lista sem iniciar) (p200). Python: identificar o gerenciador
  antes de lançar o interpretador (`pymanager list` ou `py -0p`) (p200).
- Instalação só depois da A05 e por fonte oficial: Git (`winget install --id Git.Git -e
  --source winget`), Python pelo gerenciador oficial, Node só se exigido (LTS), WSL
  (`wsl --install`, elevação, possível reinício), Claude Code e Codex pelos instaladores
  oficiais conferindo endereço e integridade antes de executar (p200–201). Versão
  instalada não prova acesso a modelos, gratuidade nem saldo (p201).
- venv sem alterar ExecutionPolicy: `python -m venv .venv`;
  `.\.venv\Scripts\python.exe -m pip --version`;
  `.\.venv\Scripts\python.exe -c "import sqlite3; print('SQLite OK')"` (p201).
- Falhas: comando não encontrado (novo terminal, PATH, todas as ocorrências); WSL parado
  (abrir pelo nome listado, não reinstalar); `&&` em PowerShell antigo; HTML no lugar do
  script; TLS no PowerShell 5.1 (TLS 1.2 ou WinGet) (p202).
- Aceite mínimo: caminhos e versões conforme a escolha, venv importa SQLite, teste
  temporário de escrita/leitura, relatório que explica como repetir (p203).
- [3.0 R14] WSL2 como padrão; `uv`; `.gitattributes` LF; PowerShell 7; `PYTHONUTF8=1`;
  fora do OneDrive; setup declarativo (`winget configure`).

## E — Modelos de registros e decisões (p204–209)
Mapa de registros persistentes (MISSION, RESOURCES, NOTES, learning-records, registry,
evidence/Axx, projects, state/state.sqlite) — "a matriz aponta para a evidência; a
evidência aponta para os artefatos; a retomada identifica o próximo passo" (p204).
Modelos de evidências, retomada, decisão de arquitetura, inventário de componente, fonte
e dependências, aprovação vinculada ao conteúdo, registro de aprendizagem — adaptados em
`assets/templates/` (hash sempre calculado do arquivo efetivo; nada de valores que
"pareçam" resultado de ferramenta) (p206).

## F — Verificação editorial e limites (p210–212)
O que o livro verificou: sintaxe de 8 blocos Python e 23 JSON; exemplos de memória,
preparação, recuperação FTS5 com autorização, derivação, Recall@k, chaves de cache e
cálculos KV, CaixaSim (24 métodos de teste, 60 casos diferenciais), valores financeiros
fictícios. O que **não** verificou: o computador do aluno, integração real de dois
provedores, inferência CAG, Headroom, MCP/hooks/plugins locais, migração do OpenSquad
(p210–212). Ambiente editorial declarado: Python 3.12.14 e SQLite 3.53.1 (não verificado
nesta skill).

## Referências verificadas (p213–219)
Prefixos: **E** documentação de ferramentas/produtos (E01–E44: Git, Python, SQLite,
OpenAI/Codex, Anthropic/Claude Code, MCP, Agent Skills, Node, instaladores) · **K**
conhecimento técnico/acadêmico (K01–K19: OWASP, SQLite, PROV-DM, RAG, ALCE, CAG,
Transformers, prompt caching, Headroom, perf_counter) · **P** normas e bibliotecas do
projeto jurídico/software (P01–P11: CPC, CDC, LGPD, EAOAB, CED, decimal, unittest, json,
JSON Schema, git-diff, git-worktree) · **S** fontes de suporte (S01–S19: WSL, git-status,
autenticação, créditos, venv, LangGraph, CrewAI, Microsoft Agent Framework, repositórios,
SemVer, backup, OpenTelemetry, OWASP LLM01, NIST AI RMF, licenças GitHub, pip).
Estado atual dos itens voláteis: `../fontes-verificadas.md`.
