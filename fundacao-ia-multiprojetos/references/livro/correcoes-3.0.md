# Documento 2.0 → 3.0: o que muda na execução

Origem: "Fundação de IA Multiprojetos 2.0 → 3.0: o que corrigir, o que acrescentar e
como reorganizar". A proposta preserva o núcleo conceitual do livro (quatro níveis de
evidência, estados honestos, provas negativas, autorização fora do modelo,
idempotência/reconciliação, aprovação por hash, PROV, marcadores reaplicados,
avaliação separada, "não medido" ≠ zero, Decimal, rigor sobre CAG) e aponta três
riscos: termos de uso das assinaturas (pessoal × produto), sigilo/LGPD com dados reais
e garantias que dependem da obediência do modelo [3.0 §1–§2].

## Como esta skill incorporou a proposta
| Tema 3.0 | Situação na skill | Onde |
|---|---|---|
| Seletor de rota; assinatura só para o titular | incorporado (kit + política) | `references/capacidades/03-provedores-modelos.md`, `fundacao/core/routing.py` |
| Créditos de API do Max; `claude -p` pela assinatura | conferido; **conflito oficial** registrado | `references/fontes-verificadas.md` §1 |
| Hooks PreToolUse com deny, `permissions.deny`, sandbox WSL2 | incorporado; corrigido o filtro `Write(...)` | `references/capacidades/08-ferramentas-hooks-mcp-skills-plugins.md`, `references/seguranca-isolamento.md`, `assets/hooks/guarda_caminho.py` |
| Campo `args` dos hooks | **verificado que existe** (3.0 não encontrara) | `references/fontes-verificadas.md` |
| Hooks do Codex | **verificado em documentação oficial** (3.0 tinha só fontes secundárias) | `references/fontes-verificadas.md` §2 |
| Contratos como código, JSON Schema, hash canônico (UTF-8, LF, NFC, JSON ordenado) | incorporado | `fundacao/core/canon.py`, `assets/templates/CONTRATO.schema.json` |
| UUIDv7 com prefixo | incorporado | `fundacao/core/ids.py` |
| MCP 2026-07-28, SDK 2.x | conferido (2.3.0) e incorporado como procedimento; execução pendente | `references/capacidades/08-ferramentas-hooks-mcp-skills-plugins.md` §3 |
| Execução durável (DBOS/LangGraph) × orquestrador próprio | comparação obrigatória em A3; kit = núcleo próprio | `references/capacidades/01-orquestracao.md` |
| Máquina de estados formal, outbox | incorporado | `assets/fundacao-kit/fundacao/core/tasks.py`, `assets/fundacao-kit/fundacao/core/events.py` |
| SQLite configurado (foreign_keys, busy_timeout, BEGIN IMMEDIATE, WAL) | incorporado | `fundacao/core/db.py` |
| Timeout real por subprocesso | incorporado | `fundacao/core/components.py` |
| Memória canônica × nativas; anti-envenenamento | incorporado | `references/capacidades/04-memoria.md` |
| RAG: unicode61 rd2, FTS por projeto, chunking estrutural, corpus/gabarito maiores | FTS por projeto e tokenizador no kit; demais como orientação | `references/capacidades/06-rag.md` |
| CAG estrito × prefix cache; CAG em CPU | incorporado; script com modo sintético | `references/capacidades/07-cag-caches.md`, `scripts/cag_kv_demo.py` |
| Normalização de uso sem dupla contagem | incorporado | `fundacao/core/usage.py` |
| Avaliação com regressão, repetições, juiz calibrado, avaliador independente | orientação + auditoria independente | `references/capacidades/06-rag.md`, `references/fluxo-c-operar.md` C10 |
| Trilha de auditoria encadeada | incorporado (`prev_hash`) | `assets/fundacao-kit/fundacao/core/events.py` |
| Módulo de privacidade (M04B) | incorporado como checklist e pontos de verificação, sem parecer | `references/privacidade-sigilo.md` |
| Backup 3-2-1-1-0, migrações por `user_version`, versões fixadas | orientação; `user_version` no kit | `references/capacidades/11-manutencao-recuperacao.md` |
| Windows/WSL: WSL2 padrão, uv, LF, PYTHONUTF8 | orientação | `references/capacidades/11-manutencao-recuperacao.md` |
| Projeto jurídico: fonte única, verificador de citações, regra única de desconto | orientação + R60 | `livro/m07-juridico.md` |
| Engenharia reversa: técnicas nomeadas, sala limpa, ponte com OpenSquad | orientação (Fluxo B) | `references/fluxo-b-adaptar.md` |
| Requisitos R52–R60 e limiares/validade | incorporado à matriz | `assets/templates/MATRIZ-REQUISITOS.csv` |
| Mapeamento R12, R15, R17 → A12 | registrado na coluna de aulas | `references/requisitos.md` |
| Duas trilhas (essencial/avançada) | usada como ordem, sem remover capacidades | `references/fluxo-a-implantar.md` A5 |
| Contrato comum + prompts-delta ("executar-aula") | **substituído por esta skill**: o contrato comum está no SKILL.md e nos fluxos | [Decisão] |

## O que continua só como recomendação ou não verificado
DBOS, docxtpl, promptfoo, restic/Kopia, sqlite-vec, modelos de embedding e limiares
numéricos são recomendações de engenharia a validar no protótipo; fatos regulatórios e
de planos citados na 3.0 (LGPD/ANPD, CFOAB, PL 2.338, treinamento por plano, CNJ
615/2025, Headroom, "agent teams") não foram verificados nesta skill [3.0 §9].
