# fundacao-ia-multiprojetos — skill (Agent Skills) e entrega

Skill no formato **Agent Skills** que orienta uma IA executora (Claude Code, Codex e hosts compatíveis) a
**implantar, adaptar, verificar e manter** uma fundação técnica reutilizável para operar vários projetos com IA:
núcleo com contratos, projetos isolados criados por modelo, orquestração com retomada, agentes, dois ou mais
provedores, memória persistente, GOLD, RAG, CAG, hooks, MCP, skills, plugins, consumo, observabilidade, backup
e restauração. Segue o livro *Fundação de IA Multiprojetos 2.0* (do próprio titular) com as correções 3.0, e
traz um **kit de referência** em Python + SQLite (biblioteca padrão) que implementa os contratos, com 166 testes
de conformidade e 16 cenários determinísticos.

Versão: **1.4.3** (19/10/2026) · kit de referência 1.4.1 · Licença: **MIT** (`LICENSE`).

## O que há aqui

| Pasta | Conteúdo |
|---|---|
| `fundacao-ia-multiprojetos/` | A skill: `SKILL.md`, `references/` (fluxos, capacidades, requisitos R01–R60, sínteses do livro), `scripts/`, `assets/` (kit, hooks, modelos) e `evals/` (cenários, avaliações, projetos fictícios de teste) |
| `entrega/` | Pacotes instaláveis (`dist/`), instalador (`instalar_skill.py`), empacotador, testes das ferramentas de entrega (`testes/`), zips de transferência, matriz de hosts, rastreabilidade, registros de avaliação e o `README-ENTREGA.md` completo |

Comece por [`entrega/README-ENTREGA.md`](entrega/README-ENTREGA.md): síntese, estados, instalação, uso,
atualização, retomada, evidências e o que ficou sem testar.

## Instalar

Pré-requisito: Python 3.10+ com SQLite/FTS5. O instalador não baixa nada, confere o hash do pacote antes de
extrair e faz a troca por renomeação (a versão anterior fica guardada).

```bash
python entrega/instalar_skill.py instalar --origem entrega/dist/fundacao-ia-multiprojetos.skill --sha256 a2382ebbbf7b65a7eb61f6f954723857600be890911a2afaf39436075575621b
python entrega/instalar_skill.py verificar --origem entrega/dist/fundacao-ia-multiprojetos.skill
```

Claude Code lê `~/.claude/skills/` (o instalador cria a cópia em `~/.agents/skills/` e uma junção ou link em
`~/.claude/skills/`). Para o claude.ai (Chat/Work), envie `entrega/transferencia/fundacao-ia-multiprojetos-1.4.3-para-claude-ai.zip`
em *Customize > Skills > Upload a skill*. Para outro computador, use `entrega/transferencia/fundacao-ia-multiprojetos-1.4.3.zip`
(traz o `.skill`, o instalador, `SHA256SUMS.txt` e um `LEIA-ME.txt`). Remoção: `python entrega/instalar_skill.py remover --confirmar`.

## Estado da verificação (1.4.3, Windows 11, Python 3.12.10)

- kit: 166 testes OK (3 pulados: link simbólico de arquivo sem modo de desenvolvedor); scripts da skill: 23 OK;
  ferramentas de entrega: 34 OK; cenários CEN-01–CEN-16: 16/16 (110/110 verificações); 258 referências conferidas,
  0 ausentes; `quick_validate` do skill-creator válido (duas variantes).
- Não testado: Linux, macOS, Python 3.10/3.11 (só simulado), chamadas reais a provedores, claude.ai e Codex como hosts,
  acionamento da skill num pedido real do host, CAG com modelo real. Detalhes em `entrega/MATRIZ-HOSTS-E-VERIFICACOES.md`.
- Auditorias: a 1.4.2 passou por uma auditoria final independente (só leitura, cópias e perfis descartáveis), com
  veredito *aprovada com ressalvas* — dez achados menores (P3), nenhum P1 ou P2 —, todos corrigidos na 1.4.3 com
  regressões que falham na 1.4.2 (`entrega/testes/test_auditoria_final_1_4_2.py` e
  `fundacao-ia-multiprojetos/assets/fundacao-kit/tests/test_auditoria_final_1_4_2.py`).

## Sobre esta cópia pública

Este repositório é uma cópia **saneada** do projeto de desenvolvimento, publicada por decisão do titular:

- ficaram de fora o workspace de desenvolvimento (iterações, cópias congeladas, sondas e registros de auditoria) e a
  pasta `entrega/auditoria/` (relatórios de auditoria, inclusive os recebidos de terceiros, e as respostas);
- nos arquivos de texto, o nome de usuário, o nome da máquina e os caminhos locais foram substituídos por
  `<usuario>`, `<maquina>`, `<raiz-do-projeto>` e `<pasta-de-desenvolvimento>`; os pacotes e zips são os originais,
  byte a byte (os hashes citados nos textos continuam válidos);
- citações a `auditoria/…` ou ao workspace nos textos da entrega referem-se a arquivos que só existem no projeto original.

Tudo o que a skill e o kit fazem foi testado só em ambientes descartáveis, com dados fictícios. Os exemplos jurídicos
são didáticos: a skill não redige, revisa nem libera peças ou cálculos jurídicos reais, e não substitui a documentação
oficial vigente para decisões de custo e termos.
